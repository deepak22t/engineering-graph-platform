"""Minimal Artifact and ArtifactVersion application records."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from packages.artifacts.contracts import ArtifactKind, ArtifactScope, ArtifactStatus
from packages.domain.normalization import normalize_timestamp


class Artifact(BaseModel):
    """One logical input source within a mandatory Cisco topology scope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    scope: ArtifactScope
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return normalize_timestamp(value)


class ArtifactVersion(BaseModel):
    """One immutable, stored revision of an Artifact's original bytes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    artifact_id: UUID
    version_number: int = Field(ge=1)
    original_filename: str = Field(min_length=1, max_length=1024)
    artifact_kind: ArtifactKind
    content_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)
    sha256_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    storage_key: str = Field(min_length=1, max_length=1024)
    status: ArtifactStatus = ArtifactStatus.UPLOADED
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("original_filename", "content_type", "storage_key")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank.")
        return value

    @field_validator("uploaded_at", "created_at", "updated_at")
    @classmethod
    def normalize_timestamps(cls, value: datetime) -> datetime:
        return normalize_timestamp(value)
