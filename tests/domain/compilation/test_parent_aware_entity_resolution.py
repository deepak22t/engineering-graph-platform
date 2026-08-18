"""Tests for dependency-aware Interface identity resolution."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from packages.domain.compilation import (
    CanonicalSnapshot,
    CompilationInput,
    EntityResolutionStatus,
    TypedPropertyCandidate,
    TypedPropertyCompilationResult,
    resolve_entity_identities,
)
from packages.domain.entities import DeviceEntity, SiteEntity
from packages.domain.entities.properties import (
    ComponentProperties,
    DeviceProperties,
    InterfaceProperties,
    SiteProperties,
)
from packages.domain.enums import EntityType, ExtractionMethod, RelationshipType
from packages.domain.evidence import Evidence, SourceLocation
from packages.domain.identity import (
    ComponentIdentity,
    DeviceIdentity,
    InterfaceIdentity,
    SiteIdentity,
)
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


def _candidate(proposal_id: UUID, entity_type: EntityType, properties) -> TypedPropertyCandidate:
    return TypedPropertyCandidate(
        entity_type=entity_type,
        subject_proposal_id=proposal_id,
        properties=properties,
        attribute_proposal_ids=(uuid4(),),
    )


def _has_interface(device_id: UUID, interface_id: UUID, line: int) -> RelationshipProposal:
    return RelationshipProposal(
        relationship_type=RelationshipType.HAS_INTERFACE,
        source_proposal_id=device_id,
        target_proposal_id=interface_id,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(line)],
    )


def _input(
    relationships: list[RelationshipProposal],
    *,
    entities: tuple[DeviceEntity | SiteEntity, ...] = (),
) -> CompilationInput:
    extraction = ExtractionResult(
        artifact_id=ARTIFACT_ID,
        artifact_version_id=ARTIFACT_VERSION_ID,
        artifact_version_number=1,
        artifact_kind="cisco_ios_running_config",
        artifact_checksum="a" * 64,
        scope=SCOPE,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_name="test-parser",
        extractor_version="1",
        relationship_proposals=relationships,
    )
    return CompilationInput(
        extraction_result=extraction,
        canonical_snapshot=CanonicalSnapshot(scope=SCOPE, entities=entities),
    )


def test_interface_resolves_from_exactly_one_resolved_has_interface_parent() -> None:
    device_id, interface_id = uuid4(), uuid4()
    candidates = TypedPropertyCompilationResult(
        candidates=(
            _candidate(
                interface_id,
                EntityType.INTERFACE,
                InterfaceProperties(interface_name="Gi0/1", interface_type="ethernet"),
            ),
            _candidate(
                device_id,
                EntityType.DEVICE,
                DeviceProperties(hostname="router-01"),
            ),
        )
    )

    output = resolve_entity_identities(
        _input([_has_interface(device_id, interface_id, 10)]), candidates
    )

    device, interface = output.resolutions
    assert device.status is EntityResolutionStatus.NEW_CANDIDATE
    assert interface.status is EntityResolutionStatus.NEW_CANDIDATE
    assert isinstance(interface.identity, InterfaceIdentity)
    assert interface.identity.parent_device_identity == device.identity
    assert output.findings == ()


def test_interface_with_multiple_parent_claims_remains_unresolved() -> None:
    first_device_id, second_device_id, interface_id = uuid4(), uuid4(), uuid4()
    candidates = TypedPropertyCompilationResult(
        candidates=(
            _candidate(
                first_device_id,
                EntityType.DEVICE,
                DeviceProperties(hostname="router-01"),
            ),
            _candidate(
                second_device_id,
                EntityType.DEVICE,
                DeviceProperties(hostname="router-02"),
            ),
            _candidate(
                interface_id,
                EntityType.INTERFACE,
                InterfaceProperties(interface_name="Gi0/1", interface_type="ethernet"),
            ),
        )
    )

    output = resolve_entity_identities(
        _input(
            [
                _has_interface(first_device_id, interface_id, 10),
                _has_interface(second_device_id, interface_id, 20),
            ]
        ),
        candidates,
    )

    interface = output.resolutions[-1]
    assert interface.status is EntityResolutionStatus.UNRESOLVED
    assert interface.identity is None
    assert output.findings[-1].code == "unresolved_entity_identity"


def test_duplicate_equivalent_parent_claims_still_mean_one_parent() -> None:
    device_id, interface_id = uuid4(), uuid4()
    relation = _has_interface(device_id, interface_id, 10)
    candidates = TypedPropertyCompilationResult(
        candidates=(
            _candidate(device_id, EntityType.DEVICE, DeviceProperties(hostname="router-01")),
            _candidate(
                interface_id,
                EntityType.INTERFACE,
                InterfaceProperties(interface_name="Gi0/1", interface_type="ethernet"),
            ),
        )
    )

    output = resolve_entity_identities(_input([relation, relation]), candidates)

    assert output.resolutions[-1].status is EntityResolutionStatus.NEW_CANDIDATE
    assert isinstance(output.resolutions[-1].identity, InterfaceIdentity)


def test_interface_can_use_verified_existing_canonical_device_parent() -> None:
    now = datetime.now(timezone.utc)
    device_identity = DeviceIdentity(scope=SCOPE, hostname="router-01")
    existing_device = DeviceEntity(
        identity=device_identity,
        display_name="Router 01",
        properties=DeviceProperties(hostname="router-01"),
        first_observed_at=now,
        last_observed_at=now,
        created_at=now,
        updated_at=now,
    )
    interface_id = uuid4()
    relation = RelationshipProposal(
        relationship_type=RelationshipType.HAS_INTERFACE,
        source_canonical_id=existing_device.id,
        target_proposal_id=interface_id,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(10)],
    )
    candidates = TypedPropertyCompilationResult(
        candidates=(
            _candidate(
                interface_id,
                EntityType.INTERFACE,
                InterfaceProperties(interface_name="Gi0/1", interface_type="ethernet"),
            ),
        )
    )

    output = resolve_entity_identities(_input([relation], entities=(existing_device,)), candidates)

    interface = output.resolutions[0]
    assert interface.status is EntityResolutionStatus.NEW_CANDIDATE
    assert isinstance(interface.identity, InterfaceIdentity)
    assert interface.identity.parent_device_identity == device_identity


def test_component_resolves_from_part_of_device_and_typed_locator() -> None:
    device_id, component_id = uuid4(), uuid4()
    relation = RelationshipProposal(
        relationship_type=RelationshipType.PART_OF,
        source_proposal_id=component_id,
        target_proposal_id=device_id,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(30)],
    )
    candidates = TypedPropertyCompilationResult(
        candidates=(
            _candidate(device_id, EntityType.DEVICE, DeviceProperties(hostname="router-01")),
            _candidate(
                component_id,
                EntityType.COMPONENT,
                ComponentProperties(component_type="module", slot="1", module="supervisor"),
            ),
        )
    )

    output = resolve_entity_identities(_input([relation]), candidates)

    component = output.resolutions[-1]
    assert component.status is EntityResolutionStatus.NEW_CANDIDATE
    assert isinstance(component.identity, ComponentIdentity)
    assert component.identity.parent_device_identity == output.resolutions[0].identity
    assert component.identity.component_locator == "1/supervisor"


def test_component_without_locator_remains_unresolved() -> None:
    device_id, component_id = uuid4(), uuid4()
    relation = RelationshipProposal(
        relationship_type=RelationshipType.PART_OF,
        source_proposal_id=component_id,
        target_proposal_id=device_id,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(30)],
    )
    candidates = TypedPropertyCompilationResult(
        candidates=(
            _candidate(device_id, EntityType.DEVICE, DeviceProperties(hostname="router-01")),
            _candidate(
                component_id,
                EntityType.COMPONENT,
                ComponentProperties(component_type="module"),
            ),
        )
    )

    output = resolve_entity_identities(_input([relation]), candidates)

    assert output.resolutions[-1].status is EntityResolutionStatus.UNRESOLVED
    assert output.findings[-1].code == "unresolved_entity_identity"


def test_verified_existing_canonical_site_reference_matches_without_rebuilding_identity() -> None:
    now = datetime.now(timezone.utc)
    site = SiteEntity(
        identity=SiteIdentity(scope=SCOPE, site_code="in-del-01"),
        display_name="Delhi",
        properties=SiteProperties(site_type="datacenter"),
        first_observed_at=now,
        last_observed_at=now,
        created_at=now,
        updated_at=now,
    )
    candidate = TypedPropertyCandidate(
        entity_type=EntityType.SITE,
        subject_canonical_id=site.id,
        properties=SiteProperties(site_type="datacenter"),
        attribute_proposal_ids=(uuid4(),),
    )

    output = resolve_entity_identities(
        _input([], entities=(site,)),
        TypedPropertyCompilationResult(candidates=(candidate,)),
    )

    resolution = output.resolutions[0]
    assert resolution.status is EntityResolutionStatus.MATCHED_EXISTING
    assert resolution.canonical_entity_id == site.id
    assert resolution.identity == site.identity
