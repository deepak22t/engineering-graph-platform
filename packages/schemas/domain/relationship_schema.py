"""Schemas for relationship creation requests and response payloads."""

from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from packages.domain.enums import RelationshipType
from packages.domain.ids import generate_relationship_id
from packages.domain.relationships import Relationship


class CreateRelationshipRequest(BaseModel):
    """Payload schema for creating a new canonical directed relationship."""

    relationship_type: RelationshipType
    source_id: UUID
    target_id: UUID
    attributes: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_different_source_and_target(self) -> "CreateRelationshipRequest":
        """Prevent self-referential relationship payloads."""
        if self.source_id == self.target_id:
            raise ValueError("source_id and target_id must be different entities.")
        return self

    def to_relationship(self) -> Relationship:
        """Convert payload to a canonical Relationship instance with deterministic ID."""
        rel_id = generate_relationship_id(
            self.relationship_type, self.source_id, self.target_id
        )
        now = datetime.now(timezone.utc)
        return Relationship(
            id=rel_id,
            relationship_type=self.relationship_type,
            source_id=self.source_id,
            target_id=self.target_id,
            attributes=self.attributes,
            created_at=now,
            updated_at=now,
        )


class RelationshipResponse(BaseModel):
    """API response payload schema for a relationship."""

    id: UUID
    relationship_type: RelationshipType
    source_id: UUID
    target_id: UUID
    attributes: dict[str, object]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_relationship(cls, relationship: Relationship) -> "RelationshipResponse":
        """Construct response schema from a canonical Relationship instance."""
        return cls(
            id=relationship.id,
            relationship_type=relationship.relationship_type,
            source_id=relationship.source_id,
            target_id=relationship.target_id,
            attributes=relationship.attributes,
            created_at=relationship.created_at,
            updated_at=relationship.updated_at,
        )
