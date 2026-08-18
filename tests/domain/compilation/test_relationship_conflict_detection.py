"""Tests for evidence-backed relationship conflict detection."""

from uuid import UUID, uuid4

from packages.domain.compilation import (
    CanonicalSnapshot,
    CompilationInput,
    EntityResolution,
    EntityResolutionResult,
    EntityResolutionStatus,
    TypedPropertyCandidate,
    detect_relationship_conflicts,
)
from packages.domain.entities import (
    AddressFamily,
    InterfaceProperties,
    IPAddressProperties,
    VlanProperties,
)
from packages.domain.enums import EntityType, ExtractionMethod, RelationshipType
from packages.domain.evidence import Evidence, SourceLocation
from packages.domain.identity import (
    DeviceIdentity,
    InterfaceIdentity,
    IPIdentity,
    NetworkIdentity,
    VlanIdentity,
)
from packages.domain.ids import generate_entity_id
from packages.domain.proposals import ExtractionResult, RelationshipProposal
from packages.domain.scope import GraphScope

ARTIFACT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ARTIFACT_VERSION_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SCOPE = GraphScope(
    organization_id=UUID("11111111-1111-1111-1111-111111111111"),
    project_id=UUID("22222222-2222-2222-2222-222222222222"),
    environment="production",
    site_id=UUID("33333333-3333-3333-3333-333333333333"),
)


def _evidence(line: int) -> Evidence:
    return Evidence(
        source_artifact_id=ARTIFACT_ID,
        source_artifact_version="1",
        source_artifact_checksum="a" * 64,
        source_location=SourceLocation(line_start=line),
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        confidence=0.95,
    )


def _relationship(
    relationship_type: RelationshipType,
    source_id: UUID,
    target_id: UUID,
    line: int,
    *,
    attributes: dict[str, object] | None = None,
) -> RelationshipProposal:
    return RelationshipProposal(
        relationship_type=relationship_type,
        source_proposal_id=source_id,
        target_proposal_id=target_id,
        proposed_attributes=attributes or {},
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(line)],
    )


def _resolution(
    entity_type: EntityType,
    proposal_id: UUID,
    properties,
    identity,
) -> EntityResolution:
    return EntityResolution(
        candidate=TypedPropertyCandidate(
            entity_type=entity_type,
            subject_proposal_id=proposal_id,
            properties=properties,
            attribute_proposal_ids=(uuid4(),),
        ),
        status=EntityResolutionStatus.NEW_CANDIDATE,
        identity=identity,
        canonical_entity_id=generate_entity_id(identity),
    )


def _input(
    proposals: list[RelationshipProposal],
    *,
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
        canonical_snapshot=CanonicalSnapshot(scope=SCOPE),
    )


def _interfaces() -> tuple[UUID, UUID, EntityResolution, EntityResolution]:
    first_id, second_id = uuid4(), uuid4()
    parent = DeviceIdentity(scope=SCOPE, hostname="router-01")
    first_identity = InterfaceIdentity(
        scope=SCOPE,
        parent_device_identity=parent,
        interface_name="eth0",
    )
    second_identity = InterfaceIdentity(
        scope=SCOPE,
        parent_device_identity=parent,
        interface_name="eth1",
    )
    return (
        first_id,
        second_id,
        _resolution(
            EntityType.INTERFACE,
            first_id,
            InterfaceProperties(interface_name="eth0", interface_type="ethernet"),
            first_identity,
        ),
        _resolution(
            EntityType.INTERFACE,
            second_id,
            InterfaceProperties(interface_name="eth1", interface_type="ethernet"),
            second_identity,
        ),
    )


def test_ip_attached_to_two_interfaces_creates_cardinality_conflict() -> None:
    first_id, second_id, first, second = _interfaces()
    ip_id = uuid4()
    network = NetworkIdentity(scope=SCOPE, cidr="10.0.0.0/24")
    ip_identity = IPIdentity(
        scope=SCOPE,
        network_identity=network,
        address="10.0.0.10",
    )
    ip_address = _resolution(
        EntityType.IP,
        ip_id,
        IPAddressProperties(address="10.0.0.10", address_family=AddressFamily.IPV4),
        ip_identity,
    )
    proposals = [
        _relationship(RelationshipType.ATTACHED_TO, ip_id, first_id, 10),
        _relationship(RelationshipType.ATTACHED_TO, ip_id, second_id, 20),
    ]

    output = detect_relationship_conflicts(
        _input(proposals),
        EntityResolutionResult(resolutions=(ip_address, first, second)),
    )

    assert len(output.conflicts) == 1
    conflict = output.conflicts[0]
    assert conflict.subject_id == ip_address.canonical_entity_id
    assert conflict.relationship == "ATTACHED_TO:source_cardinality"
    assert conflict.conflict_type.value == "relationship"
    assert conflict.status.value == "open"
    assert len(conflict.competing_claims) == 2
    assert (
        conflict.competing_claims[0].evidence_ids
        != conflict.competing_claims[1].evidence_ids
    )


def test_symmetric_duplicate_with_incompatible_attributes_creates_conflict() -> None:
    first_id, second_id, first, second = _interfaces()
    proposals = [
        _relationship(
            RelationshipType.CONNECTED_TO,
            first_id,
            second_id,
            10,
            attributes={"medium": "copper"},
        ),
        _relationship(
            RelationshipType.CONNECTED_TO,
            second_id,
            first_id,
            20,
            attributes={"medium": "fiber"},
        ),
    ]

    output = detect_relationship_conflicts(
        _input(proposals, artifact_kind="cdp_neighbors_detail"),
        EntityResolutionResult(resolutions=(first, second)),
    )

    assert len(output.conflicts) == 1
    conflict = output.conflicts[0]
    assert conflict.relationship is not None
    assert conflict.relationship.endswith(":attributes")
    assert [claim.value for claim in conflict.competing_claims] == [
        '{"medium":"copper"}',
        '{"medium":"fiber"}',
    ]
    assert all(claim.evidence_ids for claim in conflict.competing_claims)


def test_equivalent_symmetric_claims_are_not_a_conflict() -> None:
    first_id, second_id, first, second = _interfaces()
    proposals = [
        _relationship(
            RelationshipType.CONNECTED_TO,
            first_id,
            second_id,
            10,
            attributes={"state": " UP "},
        ),
        _relationship(
            RelationshipType.CONNECTED_TO,
            second_id,
            first_id,
            20,
            attributes={"state": "up"},
        ),
    ]

    output = detect_relationship_conflicts(
        _input(proposals, artifact_kind="lldp_neighbors_detail"),
        EntityResolutionResult(resolutions=(first, second)),
    )

    assert output.conflicts == ()


def test_multiple_vlan_memberships_follow_current_many_to_many_policy() -> None:
    interface_id, _, interface, _ = _interfaces()
    first_vlan_id, second_vlan_id = uuid4(), uuid4()
    first_identity = VlanIdentity(scope=SCOPE, vlan_id=10)
    second_identity = VlanIdentity(scope=SCOPE, vlan_id=20)
    first_vlan = _resolution(
        EntityType.VLAN,
        first_vlan_id,
        VlanProperties(vlan_id=10),
        first_identity,
    )
    second_vlan = _resolution(
        EntityType.VLAN,
        second_vlan_id,
        VlanProperties(vlan_id=20),
        second_identity,
    )
    proposals = [
        _relationship(RelationshipType.MEMBER_OF, interface_id, first_vlan_id, 10),
        _relationship(RelationshipType.MEMBER_OF, interface_id, second_vlan_id, 20),
    ]

    output = detect_relationship_conflicts(
        _input(proposals),
        EntityResolutionResult(resolutions=(interface, first_vlan, second_vlan)),
    )

    assert output.conflicts == ()
