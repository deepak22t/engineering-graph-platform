"""Engineering scope and canonical-identity context for graph entities.

This is domain context only. It does not implement authentication, RBAC, or
tenant authorization.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from packages.domain.enums import EntityType
from packages.domain.normalization import normalize_text


class GraphScope(BaseModel):
    """The organization and deployment context that owns an entity."""

    model_config = ConfigDict(frozen=True)

    organization_id: UUID
    project_id: UUID
    environment: str = Field(min_length=1, max_length=64)
    site_id: UUID | None = None

    @field_validator("environment")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        return normalize_text(value)


class CanonicalIdentity(BaseModel):
    """The immutable identity context of a canonical entity."""

    model_config = ConfigDict(frozen=True)

    entity_id: UUID
    entity_type: EntityType
    scope: GraphScope
