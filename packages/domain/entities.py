"""Entity models for the canonical engineering graph.

An Entity represents a node in the graph (e.g. Device, Interface, Network).
Entities are immutable once created. An EvidenceBackedEntity attaches a full
provenance chain and confidence score to an entity.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from packages.domain.enums import EntityType
from packages.domain.evidence import Confidence, Evidence


class Entity(BaseModel):
    """Canonical node in the engineering graph."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    entity_type: EntityType
    name: str = Field(min_length=1)
    attributes: dict[str, object] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class EvidenceBackedEntity(BaseModel):
    """An entity with its full provenance chain and confidence assessment."""

    entity: Entity
    evidence: list[Evidence] = Field(min_length=1)
    confidence: Confidence

    @property
    def id(self) -> UUID:
        return self.entity.id

    @property
    def entity_type(self) -> EntityType:
        return self.entity.entity_type
