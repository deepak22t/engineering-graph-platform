"""Tests for Phase 5 scope-safe typed entity resolution."""

from datetime import datetime, timezone
from uuid import UUID

from packages.domain.compilation import (
    CanonicalSnapshot,
    CompilationInput,
    EntityResolutionStatus,
    TypedPropertyCandidate,
    TypedPropertyCompilationResult,
    resolve_entity_identities,
)
from packages.domain.entities import DeviceEntity
from packages.domain.entities.properties import (
    AddressFamily,
    DeviceProperties,
    InterfaceProperties,
    NetworkProperties,
    VlanProperties,
)
from packages.domain.enums import EntityType, ExtractionMethod
from packages.domain.identity import DeviceIdentity
from packages.domain.proposals import ExtractionResult
from packages.domain.scope import GraphScope

ARTIFACT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ARTIFACT_VERSION_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
PROPOSAL_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
SCOPE = GraphScope(
    organization_id=UUID("11111111-1111-1111-1111-111111111111"),
    project_id=UUID("22222222-2222-2222-2222-222222222222"),
    environment="production",
    site_id=UUID("33333333-3333-3333-3333-333333333333"),
)


def _input(*, scope: GraphScope = SCOPE, entities=()) -> CompilationInput:
    return CompilationInput(
        extraction_result=ExtractionResult(
            artifact_id=ARTIFACT_ID,
            artifact_version_id=ARTIFACT_VERSION_ID,
            artifact_version_number=1,
            artifact_kind="cisco_ios_running_config",
            artifact_checksum="a" * 64,
            scope=scope,
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_name="test-parser",
            extractor_version="1",
        ),
        canonical_snapshot=CanonicalSnapshot(scope=scope, entities=entities),
    )


def _candidate(entity_type: EntityType, properties) -> TypedPropertyCandidate:
    return TypedPropertyCandidate(
        entity_type=entity_type,
        subject_proposal_id=PROPOSAL_ID,
        properties=properties,
        attribute_proposal_ids=(PROPOSAL_ID,),
    )


def test_same_typed_device_identity_matches_exactly_one_same_scope_entity() -> None:
    identity = DeviceIdentity(scope=SCOPE, hostname="router-01")
    now = datetime.now(timezone.utc)
    existing = DeviceEntity(
        identity=identity,
        display_name="existing router",
        properties=DeviceProperties(hostname="router-01"),
        first_observed_at=now,
        last_observed_at=now,
        created_at=now,
        updated_at=now,
    )
    properties = TypedPropertyCompilationResult(
        candidates=(
            _candidate(EntityType.DEVICE, DeviceProperties(hostname="router-01")),
        )
    )

    output = resolve_entity_identities(_input(entities=(existing,)), properties)

    resolution = output.resolutions[0]
    assert resolution.status is EntityResolutionStatus.MATCHED_EXISTING
    assert resolution.canonical_entity_id == existing.id
    assert resolution.identity == identity


def test_new_device_identity_uses_stable_uuid5_and_not_display_name() -> None:
    properties = TypedPropertyCompilationResult(
        candidates=(
            _candidate(EntityType.DEVICE, DeviceProperties(hostname="router-01")),
        )
    )

    first = resolve_entity_identities(_input(), properties).resolutions[0]
    second = resolve_entity_identities(_input(), properties).resolutions[0]

    assert first.status is EntityResolutionStatus.NEW_CANDIDATE
    assert first.canonical_entity_id == second.canonical_entity_id
    assert first.canonical_entity_id.version == 5


def test_same_hostname_in_another_scope_receives_another_identity() -> None:
    other_scope = SCOPE.model_copy(update={"environment": "development"})
    properties = TypedPropertyCompilationResult(
        candidates=(
            _candidate(EntityType.DEVICE, DeviceProperties(hostname="router-01")),
        )
    )

    production = resolve_entity_identities(_input(), properties).resolutions[0]
    development = resolve_entity_identities(_input(scope=other_scope), properties).resolutions[0]

    assert production.status is EntityResolutionStatus.NEW_CANDIDATE
    assert development.status is EntityResolutionStatus.NEW_CANDIDATE
    assert production.canonical_entity_id != development.canonical_entity_id


def test_network_and_site_scoped_vlan_resolve_before_dependent_entity_types() -> None:
    properties = TypedPropertyCompilationResult(
        candidates=(
            _candidate(
                EntityType.VLAN,
                VlanProperties(vlan_id=100, vlan_name="users"),
            ),
            _candidate(
                EntityType.NETWORK,
                NetworkProperties(
                    cidr="10.0.0.0/24",
                    address_family=AddressFamily.IPV4,
                    network_type="lan",
                ),
            ),
        )
    )

    output = resolve_entity_identities(_input(), properties)

    assert [resolution.candidate.entity_type for resolution in output.resolutions] == [
        EntityType.NETWORK,
        EntityType.VLAN,
    ]
    assert all(
        resolution.status is EntityResolutionStatus.NEW_CANDIDATE
        for resolution in output.resolutions
    )


def test_interface_without_resolved_parent_device_stays_unresolved() -> None:
    properties = TypedPropertyCompilationResult(
        candidates=(
            _candidate(
                EntityType.INTERFACE,
                InterfaceProperties(interface_name="eth0", interface_type="ethernet"),
            ),
        )
    )

    output = resolve_entity_identities(_input(), properties)

    assert output.resolutions[0].status is EntityResolutionStatus.UNRESOLVED
    assert output.resolutions[0].identity is None
    assert [finding.code for finding in output.findings] == ["unresolved_entity_identity"]
