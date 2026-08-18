"""API request and response contracts for the Artifact Service."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from packages.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactScope,
    ArtifactStatus,
    ArtifactVersion,
)


class ArtifactUploadMetadata(BaseModel):
    """Metadata accompanying one file in POST /artifacts.

    The file bytes are transport data and are handled by the future route.
    Artifact kind is intentionally omitted because classification is server-side.
    """

    model_config = ConfigDict(extra="forbid")

    scope: ArtifactScope
    original_filename: str = Field(min_length=1, max_length=1024)

    @field_validator("original_filename")
    @classmethod
    def reject_blank_filename(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("original_filename must not be blank.")
        return value


class ArtifactResponse(BaseModel):
    """Response contract for GET /artifacts/{artifact_id}."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    scope: ArtifactScope
    created_at: datetime

    @classmethod
    def from_artifact(cls, artifact: Artifact) -> "ArtifactResponse":
        return cls.model_validate(artifact.model_dump())


class ArtifactVersionResponse(BaseModel):
    """Response contract for one immutable artifact version."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    artifact_id: UUID
    version_number: int
    original_filename: str
    artifact_kind: ArtifactKind
    content_type: str
    size_bytes: int
    sha256_checksum: str
    status: ArtifactStatus
    uploaded_at: datetime
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_version(cls, version: ArtifactVersion) -> "ArtifactVersionResponse":
        return cls.model_validate(version.model_dump(exclude={"storage_key"}))


class ArtifactUploadResponse(BaseModel):
    """Response contract shared by both artifact upload operations."""

    model_config = ConfigDict(extra="forbid")

    artifact: ArtifactResponse
    version: ArtifactVersionResponse

    @classmethod
    def from_records(cls, artifact: Artifact, version: ArtifactVersion) -> "ArtifactUploadResponse":
        return cls(
            artifact=ArtifactResponse.from_artifact(artifact),
            version=ArtifactVersionResponse.from_version(version),
        )
