"""Tests for executable relationship specifications."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from packages.domain.entities import (
    DeviceEntity,
    DeviceProperties,
    InterfaceEntity,
    InterfaceProperties,
)
from packages.domain.enums import EntityType, RelationshipType
from packages.domain.identity import DeviceIdentity, InterfaceIdentity
from packages.domain.relationship_specs import RELATIONSHIP_SPECS, validate_relationship
from packages.domain.relationships import Relationship
from packages.domain.scope import GraphScope
from packages.domain.validation import FindingSeverity, ValidationFinding


def scope():
    return GraphScope(
        organization_id=uuid.UUID(int=1),
        project_id=uuid.UUID(int=2),
        environment="prod",
        site_id=uuid.UUID(int=3),
    )


def device(name):
    now = datetime.now(timezone.utc)
    identity = DeviceIdentity(scope=scope(), hostname=name)
    return DeviceEntity(
        identity=identity,
        display_name=name,
        properties=DeviceProperties(hostname=name),
        first_observed_at=now,
        last_observed_at=now,
        created_at=now,
        updated_at=now,
    )


def interface(parent, name):
    now = datetime.now(timezone.utc)
    identity = InterfaceIdentity(
        scope=parent.scope, parent_device_identity=parent.identity, interface_name=name
    )
    return InterfaceEntity(
        identity=identity,
        display_name=name,
        properties=InterfaceProperties(interface_name=name, interface_type="ethernet"),
        first_observed_at=now,
        last_observed_at=now,
        created_at=now,
        updated_at=now,
    )


def rel(kind, source, target, **attributes):
    now = datetime.now(timezone.utc)
    return Relationship(
        id=uuid.uuid4(),
        relationship_type=kind,
        source_id=source.id,
        target_id=target.id,
        attributes=attributes,
        created_at=now,
        updated_at=now,
    )


def test_all_relationships_have_executable_specs():
    assert set(RELATIONSHIP_SPECS) == set(RelationshipType)


def test_invalid_endpoint_types_are_reported():
    first, second = device("r1"), device("r2")
    findings_relationship = rel(RelationshipType.HAS_INTERFACE, first, second)
    findings = validate_relationship(findings_relationship, first, second, [])
    assert findings[0].code == "invalid_endpoint_types"
    assert isinstance(findings[0], ValidationFinding)
    assert findings[0].severity is FindingSeverity.ERROR
    assert findings[0].subject_id == findings_relationship.id


def test_connected_to_reverse_duplicate_is_prevented():
    parent = device("r1")
    first, second = interface(parent, "eth0"), interface(parent, "eth1")
    existing = rel(RelationshipType.CONNECTED_TO, first, second)
    findings = validate_relationship(
        rel(RelationshipType.CONNECTED_TO, second, first), second, first, [existing]
    )
    assert any(f.code == "duplicate_relationship" for f in findings)


def test_has_interface_target_cardinality_is_enforced():
    first, second, port = device("r1"), device("r2"), interface(device("r3"), "eth0")
    existing = rel(RelationshipType.HAS_INTERFACE, first, port)
    findings = validate_relationship(
        rel(RelationshipType.HAS_INTERFACE, second, port), second, port, [existing]
    )
    assert any(f.code == "target_cardinality" for f in findings)


def test_per_relationship_self_loop_and_attribute_rules_are_enforced():
    parent = device("r1")
    port = interface(parent, "eth0")
    findings = validate_relationship(
        rel(RelationshipType.CONNECTED_TO, port, port, unsupported=True), port, port, []
    )
    assert {f.code for f in findings} == {"self_loop_forbidden", "unknown_attributes"}


def test_endpoint_pair_rules_and_entity_ids_are_enforced():
    source = SimpleNamespace(id=uuid.uuid4(), entity_type=EntityType.DEVICE)
    target = SimpleNamespace(id=uuid.uuid4(), entity_type=EntityType.VLAN)
    invalid_pair = Relationship(
        id=uuid.uuid4(),
        relationship_type=RelationshipType.MEMBER_OF,
        source_id=source.id,
        target_id=target.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    findings = validate_relationship(invalid_pair, source, target, [])
    assert any(f.code == "invalid_endpoint_types" for f in findings)

    parent = device("r1")
    port = interface(parent, "eth0")
    valid_edge = rel(RelationshipType.HAS_INTERFACE, parent, port)
    mismatched_edge = valid_edge.model_copy(update={"source_id": uuid.uuid4()})
    findings = validate_relationship(mismatched_edge, parent, port, [])
    assert any(f.code == "endpoint_identity_mismatch" for f in findings)
