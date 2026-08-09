"""Immutable handoff contracts from ingestion to deterministic extraction."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from packages.artifacts.contracts import ArtifactKind, ArtifactScope


class ExtractionInput(BaseModel):
    """A validated source reference for one later deterministic extraction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: UUID
    artifact_version_id: UUID
    version_number: int = Field(ge=1)
    scope: ArtifactScope
    artifact_kind: ArtifactKind
    sha256_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    original_filename: str = Field(min_length=1, max_length=1024)
    storage_key: str = Field(min_length=1, max_length=1024)
    adapter_name: str = Field(min_length=1, max_length=255)
    adapter_version: str = Field(min_length=1, max_length=255)

    @field_validator(
        "original_filename",
        "storage_key",
        "adapter_name",
        "adapter_version",
    )
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank.")
        return value
