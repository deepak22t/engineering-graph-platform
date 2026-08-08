"""Tests for typed, scope-aware entity identity and UUIDv5 generation."""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from packages.domain.entities import DeviceEntity, DeviceProperties
from packages.domain.identity import (
    ComponentIdentity,
    ConnectionIdentity,
    ContainerIdentity,
    DeviceIdentity,
    FirewallIdentity,
    InterfaceIdentity,
    IPIdentity,
    NetworkIdentity,
    RouteIdentity,
    ServiceIdentity,
    SiteIdentity,
    VlanIdentity,
)
from packages.domain.ids import generate_entity_id
from packages.domain.scope import GraphScope
from packages.schemas.domain.entity_schema import CreateEntityRequest


def scope(*, environment: str = "prod", site: int | None = 1) -> GraphScope:
    return GraphScope(
        organization_id=uuid.UUID(int=10),
        project_id=uuid.UUID(int=20),
        environment=environment,
        site_id=uuid.UUID(int=site) if site is not None else None,
    )


def device(*, environment: str = "prod", site: int | None = 1, hostname: str = "router-01"):
    return DeviceIdentity(scope=scope(environment=environment, site=site), hostname=hostname)


def entity(identity, name: str = "Router 01") -> DeviceEntity:
    now = datetime.now(timezone.utc)
    return DeviceEntity(
        identity=identity,
        display_name=name,
        properties=DeviceProperties(hostname=identity.hostname or "router-01"),
        first_observed_at=now,
        last_observed_at=now,
        created_at=now,
        updated_at=now,
    )


def test_same_normalized_identity_always_has_same_uuid5():
    first = device(hostname=" Router-01 ")
    second = device(hostname="router-01")

    assert generate_entity_id(first) == generate_entity_id(second)
    assert generate_entity_id(first).version == 5


def test_same_hostname_in_different_scopes_has_different_ids():
    identities = (
        device(environment="prod", site=1),
        device(environment="dev", site=1),
        device(environment="prod", site=2),
    )

    assert len({generate_entity_id(identity) for identity in identities}) == 3


def test_interfaces_with_same_name_on_different_devices_have_different_ids():
    first_parent = device(hostname="router-01")
    second_parent = device(hostname="router-02")
    first = InterfaceIdentity(
        scope=first_parent.scope,
        parent_device_identity=first_parent,
        interface_name=" Eth0 ",
    )
    second = InterfaceIdentity(
        scope=second_parent.scope,
        parent_device_identity=second_parent,
        interface_name="eth0",
    )

    assert generate_entity_id(first) != generate_entity_id(second)


def test_display_name_change_does_not_change_id():
    identity = device()
    assert entity(identity, "Router 01").id == entity(identity, "Core router").id


def test_identity_and_entity_are_immutable():
    identity = device()
    canonical_entity = entity(identity)

    with pytest.raises((ValidationError, TypeError)):
        identity.hostname = "router-02"
    with pytest.raises((ValidationError, TypeError)):
        canonical_entity.identity = device(hostname="router-02")


def test_arbitrary_entity_id_is_rejected_at_domain_and_api_boundary():
    identity = device()
    now = datetime.now(timezone.utc)

    with pytest.raises(ValidationError):
        DeviceEntity(
            id=uuid.uuid4(),
            identity=identity,
            display_name="Router 01",
            created_at=now,
            updated_at=now,
        )
    with pytest.raises(ValidationError):
        CreateEntityRequest(id=uuid.uuid4(), identity=identity, name="Router 01")


def test_device_requires_serial_or_site_scoped_hostname():
    with pytest.raises(ValidationError):
        DeviceIdentity(scope=scope(site=None))
    with pytest.raises(ValidationError):
        DeviceIdentity(scope=scope(site=None), hostname="router-01")


def test_each_entity_type_has_a_typed_identity_model():
    base_scope = scope()
    parent = DeviceIdentity(scope=base_scope, serial_number="SN-01")
    network = NetworkIdentity(scope=base_scope, cidr="10.0.0.9/24")
    identities = (
        parent,
        ComponentIdentity(
            scope=base_scope,
            parent_device_identity=parent,
            component_locator=" Slot 1 ",
            serial_number="MOD-01",
        ),
        InterfaceIdentity(
            scope=base_scope,
            parent_device_identity=parent,
            interface_name="Gi0/1",
        ),
        network,
        SiteIdentity(scope=base_scope, site_code="India-DC-1"),
        ServiceIdentity(
            scope=base_scope,
            service_name="inventory-api",
            namespace="platform",
        ),
        ContainerIdentity(
            scope=base_scope,
            cluster="prod-cluster",
            namespace="platform",
            workload_id="inventory-6df4",
        ),
        IPIdentity(scope=base_scope, network_identity=network, address="10.0.0.10"),
        VlanIdentity(scope=base_scope, vlan_id=100, network_identity=network),
        RouteIdentity(
            scope=base_scope,
            source_device_identity=parent,
            destination_cidr="192.168.1.9/24",
            next_hop="10.0.0.1",
        ),
        FirewallIdentity(scope=base_scope, serial_number="FW-01"),
        ConnectionIdentity(
            scope=base_scope,
            endpoint_a_identity=parent,
            endpoint_b_identity=DeviceIdentity(scope=base_scope, hostname="router-02"),
            connection_type="Fiber",
        ),
    )

    assert len(identities) == 12
    assert all(identity.identity_fields for identity in identities)


def test_connection_endpoint_order_does_not_change_id():
    first_endpoint = device(hostname="router-01")
    second_endpoint = device(hostname="router-02")
    first = ConnectionIdentity(
        scope=scope(),
        endpoint_a_identity=first_endpoint,
        endpoint_b_identity=second_endpoint,
        connection_type="fiber",
    )
    second = ConnectionIdentity(
        scope=scope(),
        endpoint_a_identity=second_endpoint,
        endpoint_b_identity=first_endpoint,
        connection_type="Fiber",
    )

    assert generate_entity_id(first) == generate_entity_id(second)


def test_site_identity_accepts_a_normalized_name_when_no_code_exists():
    identity = SiteIdentity(scope=scope(), site_name=" India DC 1 ")

    assert identity.identity_fields == {"site_name": "india dc 1"}


def test_vlan_requires_site_or_network_context():
    with pytest.raises(ValidationError):
        VlanIdentity(scope=scope(site=None), vlan_id=100)


def test_firewall_policy_requires_policy_id():
    with pytest.raises(ValidationError):
        FirewallIdentity(
            scope=scope(),
            firewall_kind="policy",
            appliance_name="edge-firewall",
        )


def test_connection_requires_typed_endpoint_identities():
    with pytest.raises(ValidationError):
        ConnectionIdentity(
            scope=scope(),
            endpoint_a_id=uuid.uuid4(),
            endpoint_b_id=uuid.uuid4(),
            connection_type="fiber",
        )
