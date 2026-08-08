"""Shared canonical entity and property validation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from packages.domain.enums import EntityType
from packages.domain.identity import EntityIdentity
from packages.domain.ids import generate_entity_id
from packages.domain.immutability import deep_freeze
from packages.domain.normalization import normalize_text, normalize_timestamp
from packages.domain.scope import CanonicalIdentity, GraphScope


class LifecycleState(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
    UNKNOWN = "unknown"


class ObservationState(str, Enum):
    OBSERVED = "observed"
    NOT_OBSERVED = "not_observed"
    STALE = "stale"
    SUPERSEDED = "superseded"
    DISPUTED = "disputed"


class EntityProperties(BaseModel):
    """Strict base for typed canonical engineering properties."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    extensions: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("extensions", mode="after")
    @classmethod
    def freeze_extensions(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        return deep_freeze(value)


class CanonicalEntity(BaseModel):
    """Immutable base for all typed canonical graph entities."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identity: EntityIdentity
    display_name: str = Field(min_length=1, max_length=255)
    properties: EntityProperties
    lifecycle_state: LifecycleState = LifecycleState.UNKNOWN
    first_observed_at: datetime
    last_observed_at: datetime
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: UUID | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalize_text(value, casefold=False)

    @field_validator(
        "first_observed_at",
        "last_observed_at",
        "valid_from",
        "valid_to",
        "created_at",
        "updated_at",
    )
    @classmethod
    def require_timezone_aware_timestamp(cls, value: datetime | None) -> datetime | None:
        return normalize_timestamp(value) if value is not None else None

    @model_validator(mode="after")
    def validate_timestamp_order(self) -> "CanonicalEntity":
        if self.first_observed_at > self.last_observed_at:
            raise ValueError("first_observed_at must not be after last_observed_at.")
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_from > self.valid_to
        ):
            raise ValueError("valid_from must not be after valid_to.")
        if self.created_at > self.updated_at:
            raise ValueError("created_at must not be after updated_at.")
        return self

    @property
    def id(self) -> UUID:
        return generate_entity_id(self.identity)

    @property
    def entity_type(self) -> EntityType:
        return self.identity.entity_type

    @property
    def scope(self) -> GraphScope:
        return self.identity.scope

    @property
    def canonical_identity(self) -> CanonicalIdentity:
        return CanonicalIdentity(entity_id=self.id, entity_type=self.entity_type, scope=self.scope)
