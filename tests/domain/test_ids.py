"""Tests for deterministic ID generation (UUIDv5)."""

import uuid

from packages.domain.enums import EntityType, RelationshipType
from packages.domain.ids import (
    PLATFORM_NAMESPACE,
    generate_entity_id,
    generate_relationship_id,
)


def test_entity_id_determinism():
    """Same entity type and canonical name must produce identical UUIDs."""
    id1 = generate_entity_id(EntityType.DEVICE, "router-core-01")
    id2 = generate_entity_id(EntityType.DEVICE, "router-core-01")
    assert id1 == id2


def test_entity_id_normalisation():
    """Whitespace and case differences must be normalised to produce identical UUIDs."""
    id1 = generate_entity_id(EntityType.DEVICE, "router-core-01")
    id2 = generate_entity_id(EntityType.DEVICE, "  Router-Core-01  ")
    assert id1 == id2


def test_entity_id_uniqueness_by_name():
    """Different entity names must produce distinct UUIDs."""
    id1 = generate_entity_id(EntityType.DEVICE, "router-core-01")
    id2 = generate_entity_id(EntityType.DEVICE, "router-core-02")
    assert id1 != id2


def test_entity_id_uniqueness_by_type():
    """Same entity name with different entity types must produce distinct UUIDs."""
    id1 = generate_entity_id(EntityType.DEVICE, "core-01")
    id2 = generate_entity_id(EntityType.INTERFACE, "core-01")
    assert id1 != id2


def test_entity_id_format():
    """Entity ID must be a valid UUIDv5 instance."""
    entity_id = generate_entity_id(EntityType.DEVICE, "test-device")
    assert isinstance(entity_id, uuid.UUID)
    assert entity_id.version == 5


def test_relationship_id_determinism():
    """Same relationship type, source, and target must produce identical UUIDs."""
    src = generate_entity_id(EntityType.DEVICE, "router-01")
    tgt = generate_entity_id(EntityType.INTERFACE, "eth0")

    rel1 = generate_relationship_id(RelationshipType.HAS_INTERFACE, src, tgt)
    rel2 = generate_relationship_id(RelationshipType.HAS_INTERFACE, src, tgt)
    assert rel1 == rel2


def test_relationship_id_directionality():
    """Reversing source and target must produce different relationship UUIDs."""
    id_a = generate_entity_id(EntityType.DEVICE, "dev-a")
    id_b = generate_entity_id(EntityType.DEVICE, "dev-b")

    rel_forward = generate_relationship_id(RelationshipType.CONNECTED_TO, id_a, id_b)
    rel_reverse = generate_relationship_id(RelationshipType.CONNECTED_TO, id_b, id_a)
    assert rel_forward != rel_reverse


def test_platform_namespace_constant():
    """Platform namespace must remain a fixed UUID."""
    assert isinstance(PLATFORM_NAMESPACE, uuid.UUID)
    assert str(PLATFORM_NAMESPACE) == "1c997747-9e9c-436d-8f0f-f2f223692e0c"
