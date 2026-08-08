"""Identifier generation for canonical engineering graph records."""

import uuid

from packages.domain.enums import RelationshipType
from packages.domain.identity import EntityIdentity

PLATFORM_NAMESPACE = uuid.UUID("1c997747-9e9c-436d-8f0f-f2f223692e0c")


def generate_entity_id(identity: EntityIdentity) -> uuid.UUID:
    """Return the deterministic UUIDv5 for a validated typed identity."""
    return uuid.uuid5(PLATFORM_NAMESPACE, identity.canonical_serialization())


def generate_relationship_id(
    relationship_type: RelationshipType,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
) -> uuid.UUID:
    """Return a deterministic UUID for a directed relationship."""
    name = f"{relationship_type.value}:{source_id}:{target_id}"
    return uuid.uuid5(PLATFORM_NAMESPACE, name)
