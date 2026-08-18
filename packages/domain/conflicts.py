"""Conflict and human-review contracts; these never overwrite canonical facts."""

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from packages.domain.normalization import normalize_text, normalize_timestamp


class ConflictType(str, Enum):
    IDENTITY = "identity"
    PROPERTY = "property"
    RELATIONSHIP = "relationship"


class ConflictStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class CompetingClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    value: str
    evidence_ids: tuple[UUID, ...] = Field(min_length=1)
    source_method: str | None = None


class Conflict(BaseModel):
    """Retains incompatible claims for future semantic review."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID = Field(default_factory=uuid4)
    subject_type: str
    subject_id: UUID | None = None
    field_path: str | None = None
    relationship: str | None = None
    competing_claims: tuple[CompetingClaim, ...] = Field(min_length=2)
    conflict_type: ConflictType
    status: ConflictStatus = ConflictStatus.OPEN
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("detected_at")
    @classmethod
    def require_aware_detected_at(cls, value: datetime) -> datetime:
        return normalize_timestamp(value)

    @model_validator(mode="after")
    def require_conflict_subject(self) -> "Conflict":
        if self.field_path is None and self.relationship is None:
            raise ValueError("Conflict requires a field_path or relationship.")
        return self


class ReviewDecision(BaseModel):
    """A traceable human decision recorded separately from source history."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID = Field(default_factory=uuid4)
    conflict_id: UUID
    decision: Literal["accept", "reject", "correct"]
    reviewer_id: UUID
    selected_claim_value: str | None = None
    corrected_value: str | None = None
    reason: str = Field(min_length=1)
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return normalize_text(value, casefold=False)

    @field_validator("selected_claim_value", "corrected_value")
    @classmethod
    def reject_blank_optional_values(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Review decision values must not be blank.")
        return value

    @field_validator("decided_at")
    @classmethod
    def require_aware_decided_at(cls, value: datetime) -> datetime:
        return normalize_timestamp(value)

    @model_validator(mode="after")
    def require_action_data(self) -> "ReviewDecision":
        if self.decision in {"accept", "reject"} and self.selected_claim_value is None:
            raise ValueError("Accept/reject decisions require selected_claim_value.")
        if self.decision == "correct" and self.corrected_value is None:
            raise ValueError("A correction decision requires corrected_value.")
        if self.decision != "correct" and self.corrected_value is not None:
            raise ValueError("Only a correction decision may include corrected_value.")
        return self
