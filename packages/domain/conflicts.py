"""Conflict and human-review contracts; these never overwrite canonical facts."""

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    evidence_ids: list[UUID] = Field(min_length=1)
    source_method: str | None = None


class Conflict(BaseModel):
    """Retains incompatible claims for future semantic review."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID = Field(default_factory=uuid4)
    subject_type: str
    subject_id: UUID | None = None
    field_path: str | None = None
    relationship: str | None = None
    competing_claims: list[CompetingClaim] = Field(min_length=2)
    conflict_type: ConflictType
    status: ConflictStatus = ConflictStatus.OPEN
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def require_conflict_subject(self) -> "Conflict":
        if self.field_path is None and self.relationship is None:
            raise ValueError("Conflict requires a field_path or relationship.")
        return self


class ReviewDecision(BaseModel):
    """A human decision recorded separately from the competing claims."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    decision: Literal["accept", "reject", "correct"]
    reviewer_id: UUID
    corrected_value: str | None = None
    reason: str = Field(min_length=1)
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def require_corrected_value(self) -> "ReviewDecision":
        if self.decision == "correct" and not self.corrected_value:
            raise ValueError("A correction decision requires corrected_value.")
        return self
