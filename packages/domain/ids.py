"""Deterministic ID generation for the canonical engineering graph.

Uses UUIDv5 (namespace + name → SHA-1 hash) so that the same entity or
relationship always produces the same UUID regardless of which artifact or
extractor produced it. This is the foundation of entity resolution in Phase 5.

PLATFORM_NAMESPACE must never change after the first graph is written.
"""

import uuid

from packages.domain.enums import EntityType, RelationshipType

# Fixed namespace for this platform — generated once, never regenerated.
PLATFORM_NAMESPACE = uuid.UUID("1c997747-9e9c-436d-8f0f-f2f223692e0c")


def generate_entity_id(entity_type: EntityType, canonical_name: str) -> uuid.UUID:
    """Return a deterministic UUID for an entity.

    The same entity_type + canonical_name always produces the same UUID.
    canonical_name is normalised (stripped, lowercased) before hashing so
    whitespace and case differences resolve to the same node.
    """
    name = f"{entity_type.value}:{canonical_name.strip().lower()}"
    return uuid.uuid5(PLATFORM_NAMESPACE, name)


def generate_relationship_id(
    relationship_type: RelationshipType,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
) -> uuid.UUID:
    """Return a deterministic UUID for a directed relationship.

    source → target and target → source are different relationships and
    produce different UUIDs.
    """
    name = f"{relationship_type.value}:{source_id}:{target_id}"
    return uuid.uuid5(PLATFORM_NAMESPACE, name)
