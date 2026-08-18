"""Tests for typed identity paths whose prerequisites are present in Phase 5 input."""

from uuid import UUID, uuid4

import pytest

from packages.domain.compilation import (
    CanonicalSnapshot,
    CompilationInput,
    EntityResolutionStatus,
    TypedPropertyCandidate,
    TypedPropertyCompilationResult,
    resolve_entity_identities,
)
from packages.domain.entities.properties import (
    AddressFamily,
    ConnectionProperties,
    ContainerProperties,
    FirewallProperties,
    IPAddressProperties,
    NetworkProperties,
    RouteProperties,
    ServiceProperties,
    SiteProperties,
)
from packages.domain.enums import EntityType, ExtractionMethod
from packages.domain.identity import FirewallIdentity, IPIdentity, ServiceIdentity
from packages.domain.proposals import ExtractionResult
from packages.domain.scope import GraphScope

SCOPE = GraphScope(
    organization_id=UUID("11111111-1111-1111-1111-111111111111"),
    project_id=UUID("22222222-2222-2222-2222-222222222222"),
    environment="production",
    site_id=UUID("33333333-3333-3333-3333-333333333333"),
)


def _input() -> CompilationInput:
    return CompilationInput(
        extraction_result=ExtractionResult(
            artifact_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            artifact_version_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            artifact_version_number=1,
            artifact_kind="cisco_ios_running_config",
            artifact_checksum="a" * 64,
            scope=SCOPE,
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_name="test-parser",
            extractor_version="1",
        ),
        canonical_snapshot=CanonicalSnapshot(scope=SCOPE),
    )


def _candidate(entity_type: EntityType, properties) -> TypedPropertyCandidate:
    proposal_id = uuid4()
    return TypedPropertyCandidate(
        entity_type=entity_type,
        subject_proposal_id=proposal_id,
        properties=properties,
        attribute_proposal_ids=(proposal_id,),
    )


def _network(cidr: str) -> TypedPropertyCandidate:
    return _candidate(
        EntityType.NETWORK,
        NetworkProperties(
            cidr=cidr,
            address_family=AddressFamily.IPV4,
            network_type="interface_subnet",
        ),
    )


def _ip(address: str = "10.0.0.10") -> TypedPropertyCandidate:
    return _candidate(
        EntityType.IP,
        IPAddressProperties(address=address, address_family=AddressFamily.IPV4),
    )


def test_ip_resolves_only_with_exactly_one_containing_network() -> None:
    output = resolve_entity_identities(
        _input(),
        TypedPropertyCompilationResult(candidates=(_ip(), _network("10.0.0.0/24"))),
    )

    network, ip_address = output.resolutions
    assert network.status is EntityResolutionStatus.NEW_CANDIDATE
    assert ip_address.status is EntityResolutionStatus.NEW_CANDIDATE
    assert isinstance(ip_address.identity, IPIdentity)
    assert ip_address.identity.network_identity == network.identity


def test_ip_with_overlapping_network_context_remains_unresolved() -> None:
    output = resolve_entity_identities(
        _input(),
        TypedPropertyCompilationResult(
            candidates=(
                _network("10.0.0.0/24"),
                _network("10.0.0.0/25"),
                _ip(),
            )
        ),
    )

    assert output.resolutions[-1].status is EntityResolutionStatus.UNRESOLVED
    assert output.findings[-1].code == "unresolved_entity_identity"


def test_service_resolves_only_with_explicit_application_context() -> None:
    with_application = _candidate(
        EntityType.SERVICE,
        ServiceProperties(
            service_name="inventory-api",
            service_type="api",
            application="inventory",
        ),
    )
    without_application = _candidate(
        EntityType.SERVICE,
        ServiceProperties(service_name="inventory-api", service_type="api"),
    )

    output = resolve_entity_identities(
        _input(),
        TypedPropertyCompilationResult(candidates=(with_application, without_application)),
    )

    assert output.resolutions[0].status is EntityResolutionStatus.NEW_CANDIDATE
    assert isinstance(output.resolutions[0].identity, ServiceIdentity)
    assert output.resolutions[1].status is EntityResolutionStatus.UNRESOLVED


def test_firewall_policy_resolves_only_with_policy_id() -> None:
    policy = _candidate(
        EntityType.FIREWALL,
        FirewallProperties(firewall_type="policy", policy_id="POLICY-101"),
    )
    appliance_without_identity = _candidate(
        EntityType.FIREWALL,
        FirewallProperties(firewall_type="appliance", vendor="cisco"),
    )

    output = resolve_entity_identities(
        _input(),
        TypedPropertyCompilationResult(candidates=(policy, appliance_without_identity)),
    )

    assert output.resolutions[0].status is EntityResolutionStatus.NEW_CANDIDATE
    assert isinstance(output.resolutions[0].identity, FirewallIdentity)
    assert output.resolutions[1].status is EntityResolutionStatus.UNRESOLVED


@pytest.mark.parametrize(
    ("entity_type", "properties"),
    (
        (EntityType.SITE, SiteProperties(site_type="datacenter")),
        (
            EntityType.CONTAINER,
            ContainerProperties(
                workload_name="inventory-api",
                image="inventory:1",
                runtime="containerd",
            ),
        ),
        (
            EntityType.ROUTE,
            RouteProperties(
                destination_cidr="10.20.0.0/16",
                next_hop="10.0.0.1",
                protocol="static",
            ),
        ),
        (
            EntityType.CONNECTION,
            ConnectionProperties(connection_type="ethernet"),
        ),
    ),
)
def test_candidate_without_required_identity_context_remains_unresolved(
    entity_type: EntityType, properties
) -> None:
    output = resolve_entity_identities(
        _input(),
        TypedPropertyCompilationResult(candidates=(_candidate(entity_type, properties),)),
    )

    assert output.resolutions[0].status is EntityResolutionStatus.UNRESOLVED
    assert output.resolutions[0].identity is None
    assert output.findings[0].code == "unresolved_entity_identity"
