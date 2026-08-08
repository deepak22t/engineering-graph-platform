"""Relationship models for the canonical engineering graph.

A Relationship represents a directed edge between two entities in the graph
(e.g. Device HAS_INTERFACE Interface). Relationships are immutable once created.
An EvidenceBackedRelationship attaches provenance and confidence.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from packages.domain.enums import RelationshipType
from packages.domain.evidence import Confidence, Evidence
from packages.domain.immutability import deep_freeze


class Relationship(BaseModel):
    """Canonical directed edge in the engineering graph."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    relationship_type: RelationshipType
    source_id: UUID
    target_id: UUID
    attributes: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("attributes", mode="after")
    @classmethod
    def freeze_attributes(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        return deep_freeze(value)

    created_at: datetime
    updated_at: datetime


class EvidenceBackedRelationship(BaseModel):
    """A relationship with its full provenance chain and confidence assessment."""

    relationship: Relationship
    evidence: tuple[Evidence, ...] = Field(min_length=1)
    confidence: Confidence

    @property
    def id(self) -> UUID:
        return self.relationship.id

    @property
    def relationship_type(self) -> RelationshipType:
        return self.relationship.relationship_type
