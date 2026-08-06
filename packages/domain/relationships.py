"""Relationship models for the canonical engineering graph.

A Relationship represents a directed edge between two entities in the graph
(e.g. Device HAS_INTERFACE Interface). Relationships are immutable once created.
An EvidenceBackedRelationship attaches provenance and confidence.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.domain.enums import RelationshipType
from packages.domain.evidence import Confidence, Evidence


class Relationship(BaseModel):
    """Canonical directed edge in the engineering graph."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    relationship_type: RelationshipType
    source_id: UUID
    target_id: UUID
    attributes: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_no_self_loop(self) -> "Relationship":
        """Prevent self-referential relationships where source equals target."""
        if self.source_id == self.target_id:
            raise ValueError("Self-referential relationships (source_id == target_id) are not allowed.")
        return self


class EvidenceBackedRelationship(BaseModel):
    """A relationship with its full provenance chain and confidence assessment."""

    relationship: Relationship
    evidence: list[Evidence] = Field(min_length=1)
    confidence: Confidence

    @property
    def id(self) -> UUID:
        return self.relationship.id

    @property
    def relationship_type(self) -> RelationshipType:
        return self.relationship.relationship_type
