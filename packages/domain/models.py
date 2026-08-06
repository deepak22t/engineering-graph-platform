"""Canonical domain models re-export module.

All consumer modules should import domain types from here for clean, consistent imports.
"""

from packages.domain.entities import Entity, EvidenceBackedEntity
from packages.domain.enums import (
    ConfidenceLevel,
    EntityType,
    ExtractionMethod,
    RelationshipType,
)
from packages.domain.evidence import Confidence, Evidence, SourceLocation
from packages.domain.ids import (
    PLATFORM_NAMESPACE,
    generate_entity_id,
    generate_relationship_id,
)
from packages.domain.relationships import EvidenceBackedRelationship, Relationship

__all__ = [
    "EntityType",
    "RelationshipType",
    "ExtractionMethod",
    "ConfidenceLevel",
    "PLATFORM_NAMESPACE",
    "generate_entity_id",
    "generate_relationship_id",
    "SourceLocation",
    "Evidence",
    "Confidence",
    "Entity",
    "EvidenceBackedEntity",
    "Relationship",
    "EvidenceBackedRelationship",
]
