"""Structured, non-mutating validation findings."""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FindingSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ValidationFinding(BaseModel):
    """A machine-readable reason a claim cannot be safely canonicalized."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    code: str = Field(min_length=1)
    severity: FindingSeverity
    message: str = Field(min_length=1)
    subject_type: str = Field(min_length=1)
    subject_id: UUID | None = None
    proposal_id: UUID | None = None
    field_path: str | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)
    remediation_hint: str | None = None
