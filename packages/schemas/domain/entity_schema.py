"""Schemas for entity creation requests and response payloads."""

from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, Field

from packages.domain.entities import Entity
from packages.domain.enums import EntityType
from packages.domain.ids import generate_entity_id


class CreateEntityRequest(BaseModel):
    """Payload schema for creating a new canonical entity."""

    entity_type: EntityType
    name: str = Field(min_length=1, max_length=255)
    attributes: dict[str, object] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    def to_entity(self) -> Entity:
        """Convert payload to a canonical Entity instance with deterministic ID."""
        clean_name = self.name.strip()
        now = datetime.now(timezone.utc)
        return Entity(
            id=generate_entity_id(self.entity_type, clean_name),
            entity_type=self.entity_type,
            name=clean_name,
            attributes=self.attributes,
            tags=self.tags,
            created_at=now,
            updated_at=now,
        )


class EntityResponse(BaseModel):
    """API response payload schema for an entity."""

    id: UUID
    entity_type: EntityType
    name: str
    attributes: dict[str, object]
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, entity: Entity) -> "EntityResponse":
        """Construct response schema from a canonical Entity instance."""
        return cls(
            id=entity.id,
            entity_type=entity.entity_type,
            name=entity.name,
            attributes=entity.attributes,
            tags=entity.tags,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
