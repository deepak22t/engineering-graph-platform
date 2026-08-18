"""Tests for Phase 5 relationship compilation after endpoint resolution."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from packages.domain.compilation import (
    CanonicalSnapshot,
    CompilationInput,
    EntityResolution,
    EntityResolutionResult,
    EntityResolutionStatus,
    TypedPropertyCandidate,
    compile_relationship_candidates,
)
from packages.domain.entities.properties import DeviceProperties, InterfaceProperties
from packages.domain.enums import EntityType, ExtractionMethod, RelationshipType
from packages.domain.evidence import Evidence, SourceLocation
from packages.domain.identity import DeviceIdentity, InterfaceIdentity
from packages.domain.ids import generate_entity_id
from packages.domain.proposals import ExtractionResult, RelationshipProposal
from packages.domain.relationships import Relationship
from packages.domain.scope import GraphScope

ARTIFACT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ARTIFACT_VERSION_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SCOPE = GraphScope(
    organization_id=UUID("11111111-1111-1111-1111-111111111111"),
    project_id=UUID("22222222-2222-2222-2222-222222222222"),
    environment="production",
    site_id=UUID("33333333-3333-3333-3333-333333333333"),
)


def _evidence() -> Evidence:
    return Evidence(
        source_artifact_id=ARTIFACT_ID,
        source_artifact_version="1",
        source_artifact_checksum="a" * 64,
        source_location=SourceLocation(line_start=1),
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        confidence=0.95,
    )


def _proposal(
    relationship_type: RelationshipType,
    source_proposal_id: UUID,
    target_proposal_id: UUID,
    *,
    attributes: dict[str, object] | None = None,
) -> RelationshipProposal:
    return RelationshipProposal(
        relationship_type=relationship_type,
        source_proposal_id=source_proposal_id,
        target_proposal_id=target_proposal_id,
        proposed_attributes=attributes or {},
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence()],
    )


def _input(
    proposals: list[RelationshipProposal],
    *,
    existing: tuple[Relationship, ...] = (),
    artifact_kind: str = "cisco_ios_running_config",
) -> CompilationInput:
    return CompilationInput(
        extraction_result=ExtractionResult(
            artifact_id=ARTIFACT_ID,
            artifact_version_id=ARTIFACT_VERSION_ID,
            artifact_version_number=1,
            artifact_kind=artifact_kind,
            artifact_checksum="a" * 64,
            scope=SCOPE,
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_name="test-parser",
            extractor_version="1",
            relationship_proposals=proposals,
        ),
        canonical_snapshot=CanonicalSnapshot(scope=SCOPE, relationships=existing),
    )


def _device_resolution(proposal_id: UUID, hostname: str = "router-01") -> EntityResolution:
    identity = DeviceIdentity(scope=SCOPE, hostname=hostname)
    return EntityResolution(
        candidate=TypedPropertyCandidate(
            entity_type=EntityType.DEVICE,
            subject_proposal_id=proposal_id,
            properties=DeviceProperties(hostname=hostname),
            attribute_proposal_ids=(uuid4(),),
        ),
        status=EntityResolutionStatus.NEW_CANDIDATE,
        identity=identity,
        canonical_entity_id=generate_entity_id(identity),
    )


def _interface_resolution(proposal_id: UUID, parent: DeviceIdentity, name: str) -> EntityResolution:
    identity = InterfaceIdentity(
        scope=SCOPE,
        parent_device_identity=parent,
        interface_name=name,
    )
    return EntityResolution(
        candidate=TypedPropertyCandidate(
            entity_type=EntityType.INTERFACE,
            subject_proposal_id=proposal_id,
            properties=InterfaceProperties(interface_name=name, interface_type="ethernet"),
            attribute_proposal_ids=(uuid4(),),
        ),
        status=EntityResolutionStatus.NEW_CANDIDATE,
        identity=identity,
        canonical_entity_id=generate_entity_id(identity),
    )


def test_valid_resolved_has_interface_becomes_uuid5_candidate() -> None:
    device_proposal_id, interface_proposal_id = uuid4(), uuid4()
    device = _device_resolution(device_proposal_id)
    interface = _interface_resolution(interface_proposal_id, device.identity, "eth0")

    output = compile_relationship_candidates(
        _input(
            [_proposal(RelationshipType.HAS_INTERFACE, device_proposal_id, interface_proposal_id)]
        ),
        EntityResolutionResult(resolutions=(device, interface)),
    )

    assert output.findings == ()
    assert len(output.candidates) == 1
    assert output.candidates[0].relationship_type is RelationshipType.HAS_INTERFACE
    assert output.candidates[0].id.version == 5


def test_unresolved_endpoint_never_creates_a_relationship_candidate() -> None:
    device_proposal_id, interface_proposal_id = uuid4(), uuid4()
    device = _device_resolution(device_proposal_id)
    unresolved_interface = EntityResolution(
        candidate=TypedPropertyCandidate(
            entity_type=EntityType.INTERFACE,
            subject_proposal_id=interface_proposal_id,
            properties=InterfaceProperties(interface_name="eth0", interface_type="ethernet"),
            attribute_proposal_ids=(uuid4(),),
        ),
        status=EntityResolutionStatus.UNRESOLVED,
    )

    output = compile_relationship_candidates(
        _input(
            [_proposal(RelationshipType.HAS_INTERFACE, device_proposal_id, interface_proposal_id)]
        ),
        EntityResolutionResult(resolutions=(device, unresolved_interface)),
    )

    assert output.candidates == ()
    assert [finding.code for finding in output.findings] == ["unresolved_relationship_endpoint"]


def test_reverse_connected_to_proposal_becomes_one_canonical_candidate() -> None:
    first_proposal_id, second_proposal_id = uuid4(), uuid4()
    first_parent = DeviceIdentity(scope=SCOPE, hostname="router-01")
    second_parent = DeviceIdentity(scope=SCOPE, hostname="router-02")
    first = _interface_resolution(first_proposal_id, first_parent, "eth0")
    second = _interface_resolution(second_proposal_id, second_parent, "eth0")

    output = compile_relationship_candidates(
        _input(
            [
                _proposal(RelationshipType.CONNECTED_TO, first_proposal_id, second_proposal_id),
                _proposal(RelationshipType.CONNECTED_TO, second_proposal_id, first_proposal_id),
            ],
            artifact_kind="cdp_neighbors_detail",
        ),
        EntityResolutionResult(resolutions=(first, second)),
    )

    assert len(output.candidates) == 1
    assert output.findings == ()
    assert len(output.evidence_sources) == 1
    assert len(output.evidence_sources[0].proposal_ids) == 2


def test_invalid_endpoint_types_and_existing_cardinality_are_excluded() -> None:
    first_id, second_id = uuid4(), uuid4()
    first = _device_resolution(first_id, "router-01")
    second = _device_resolution(second_id, "router-02")
    invalid = compile_relationship_candidates(
        _input([_proposal(RelationshipType.HAS_INTERFACE, first_id, second_id)]),
        EntityResolutionResult(resolutions=(first, second)),
    )

    assert invalid.candidates == ()
    assert any(finding.code == "invalid_endpoint_types" for finding in invalid.findings)

    source_id, target_id = uuid4(), uuid4()
    source = _device_resolution(source_id)
    target = _interface_resolution(target_id, source.identity, "eth0")
    now = datetime.now(timezone.utc)
    existing = Relationship(
        id=uuid4(),
        relationship_type=RelationshipType.HAS_INTERFACE,
        source_id=uuid4(),
        target_id=target.canonical_entity_id,
        created_at=now,
        updated_at=now,
    )
    cardinality = compile_relationship_candidates(
        _input(
            [_proposal(RelationshipType.HAS_INTERFACE, source_id, target_id)],
            existing=(existing,),
        ),
        EntityResolutionResult(resolutions=(source, target)),
    )

    assert cardinality.candidates == ()
    assert any(finding.code == "target_cardinality" for finding in cardinality.findings)


def test_connected_to_requires_direct_cdp_or_lldp_artifact_assertion() -> None:
    first_id, second_id = uuid4(), uuid4()
    first_parent = DeviceIdentity(scope=SCOPE, hostname="router-01")
    second_parent = DeviceIdentity(scope=SCOPE, hostname="router-02")
    first = _interface_resolution(first_id, first_parent, "eth0")
    second = _interface_resolution(second_id, second_parent, "eth0")

    output = compile_relationship_candidates(
        _input([_proposal(RelationshipType.CONNECTED_TO, first_id, second_id)]),
        EntityResolutionResult(resolutions=(first, second)),
    )

    assert output.candidates == ()
    assert [finding.code for finding in output.findings] == [
        "unsupported_connected_to_artifact"
    ]


def test_connected_to_attributes_are_normalized_before_validation() -> None:
    first_id, second_id = uuid4(), uuid4()
    first_parent = DeviceIdentity(scope=SCOPE, hostname="router-01")
    second_parent = DeviceIdentity(scope=SCOPE, hostname="router-02")
    first = _interface_resolution(first_id, first_parent, "eth0")
    second = _interface_resolution(second_id, second_parent, "eth0")
    proposal = _proposal(
        RelationshipType.CONNECTED_TO,
        first_id,
        second_id,
        attributes={"medium": "  Copper ", "state": " UP ", "capacity_bps": 1_000},
    )

    output = compile_relationship_candidates(
        _input([proposal], artifact_kind="lldp_neighbors_detail"),
        EntityResolutionResult(resolutions=(first, second)),
    )

    assert output.findings == ()
    assert dict(output.candidates[0].attributes) == {
        "medium": "copper",
        "state": "up",
        "capacity_bps": 1_000,
    }


def test_self_loop_and_unknown_attributes_are_excluded() -> None:
    interface_id = uuid4()
    parent = DeviceIdentity(scope=SCOPE, hostname="router-01")
    interface = _interface_resolution(interface_id, parent, "eth0")
    proposal = _proposal(
        RelationshipType.CONNECTED_TO,
        interface_id,
        interface_id,
        attributes={"unsupported": True},
    )

    output = compile_relationship_candidates(
        _input([proposal], artifact_kind="cdp_neighbors_detail"),
        EntityResolutionResult(resolutions=(interface,)),
    )

    assert output.candidates == ()
    assert {finding.code for finding in output.findings} == {
        "self_loop_forbidden",
        "unknown_attributes",
    }


def test_newly_compiled_candidates_enforce_cardinality_together() -> None:
    first_device_id, second_device_id, interface_id = uuid4(), uuid4(), uuid4()
    first_device = _device_resolution(first_device_id, "router-01")
    second_device = _device_resolution(second_device_id, "router-02")
    interface = _interface_resolution(interface_id, first_device.identity, "eth0")

    output = compile_relationship_candidates(
        _input(
            [
                _proposal(RelationshipType.HAS_INTERFACE, first_device_id, interface_id),
                _proposal(RelationshipType.HAS_INTERFACE, second_device_id, interface_id),
            ]
        ),
        EntityResolutionResult(
            resolutions=(first_device, second_device, interface)
        ),
    )

    assert len(output.candidates) == 1
    assert output.candidates[0].source_id == first_device.canonical_entity_id
    assert any(finding.code == "target_cardinality" for finding in output.findings)


def test_invalid_connected_to_attribute_value_is_excluded() -> None:
    first_id, second_id = uuid4(), uuid4()
    first_parent = DeviceIdentity(scope=SCOPE, hostname="router-01")
    second_parent = DeviceIdentity(scope=SCOPE, hostname="router-02")
    first = _interface_resolution(first_id, first_parent, "eth0")
    second = _interface_resolution(second_id, second_parent, "eth0")
    proposal = _proposal(
        RelationshipType.CONNECTED_TO,
        first_id,
        second_id,
        attributes={"capacity_bps": True},
    )

    output = compile_relationship_candidates(
        _input([proposal], artifact_kind="cdp_neighbors_detail"),
        EntityResolutionResult(resolutions=(first, second)),
    )

    assert output.candidates == ()
    assert [finding.code for finding in output.findings] == [
        "invalid_relationship_attributes"
    ]


def test_existing_symmetric_relationship_excludes_reverse_duplicate() -> None:
    first_id, second_id = uuid4(), uuid4()
    first_parent = DeviceIdentity(scope=SCOPE, hostname="router-01")
    second_parent = DeviceIdentity(scope=SCOPE, hostname="router-02")
    first = _interface_resolution(first_id, first_parent, "eth0")
    second = _interface_resolution(second_id, second_parent, "eth0")
    now = datetime.now(timezone.utc)
    existing = Relationship(
        id=uuid4(),
        relationship_type=RelationshipType.CONNECTED_TO,
        source_id=first.canonical_entity_id,
        target_id=second.canonical_entity_id,
        created_at=now,
        updated_at=now,
    )

    output = compile_relationship_candidates(
        _input(
            [_proposal(RelationshipType.CONNECTED_TO, second_id, first_id)],
            existing=(existing,),
            artifact_kind="lldp_neighbors_detail",
        ),
        EntityResolutionResult(resolutions=(first, second)),
    )

    assert output.candidates == ()
    assert any(finding.code == "duplicate_relationship" for finding in output.findings)
