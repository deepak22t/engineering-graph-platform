"""Precise provenance and fact-level evidence models."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.domain.confidence import Confidence
from packages.domain.entities.base import ObservationState
from packages.domain.enums import ExtractionMethod


class SourceLocation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    artifact_type: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    page_number: int | None = Field(default=None, ge=1)
    json_path: str | None = None
    xpath: str | None = None
    byte_start: int | None = Field(default=None, ge=0)
    byte_end: int | None = Field(default=None, ge=0)
    bounding_box: tuple[float, float, float, float] | None = None
    sheet_name: str | None = None
    cell_range: str | None = None
    section: str | None = None

    @model_validator(mode="after")
    def validate_ranges(self) -> "SourceLocation":
        if self.line_end is not None and self.line_start is None:
            raise ValueError("line_end requires line_start.")
        if (
            self.line_start is not None
            and self.line_end is not None
            and self.line_start > self.line_end
        ):
            raise ValueError("line_start must not exceed line_end.")
        if self.byte_end is not None and self.byte_start is None:
            raise ValueError("byte_end requires byte_start.")
        if (
            self.byte_start is not None
            and self.byte_end is not None
            and self.byte_start > self.byte_end
        ):
            raise ValueError("byte_start must not exceed byte_end.")
        if self.bounding_box is not None and any(value < 0 for value in self.bounding_box):
            raise ValueError("Bounding box coordinates must be non-negative.")
        return self

    @property
    def is_precise(self) -> bool:
        return any(
            (
                self.line_start is not None,
                self.page_number is not None,
                self.json_path,
                self.xpath,
                self.byte_start is not None,
                self.bounding_box is not None,
                self.sheet_name and self.cell_range,
                self.section,
            )
        )


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID = Field(default_factory=uuid4)
    source_artifact_id: UUID
    source_artifact_version: str | None = None
    source_artifact_checksum: str | None = None
    source_location: SourceLocation = Field(default_factory=SourceLocation)
    evidence_reference: str | None = None
    extracted_value: str | None = None
    extraction_method: ExtractionMethod
    extractor_version: str
    observed_at: datetime
    observation_state: ObservationState = ObservationState.OBSERVED
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str | None = None

    @model_validator(mode="after")
    def require_verifiable_locator(self) -> "Evidence":
        if not self.source_location.is_precise and not self.evidence_reference:
            raise ValueError("Evidence requires a precise source location or evidence_reference.")
        return self


class FactAttribution(BaseModel):
    """Links one evidence record to exactly one property claim or relationship fact."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: UUID
    fact_kind: Literal["property", "relationship"]
    entity_id: UUID | None = None
    property_path: str | None = None
    relationship_id: UUID | None = None

    @model_validator(mode="after")
    def validate_fact_target(self) -> "FactAttribution":
        property_target = self.entity_id is not None and self.property_path is not None
        relationship_target = self.relationship_id is not None
        if self.fact_kind == "property" and property_target and not relationship_target:
            return self
        if self.fact_kind == "relationship" and relationship_target and not property_target:
            return self
        raise ValueError("Attribution must point to exactly one fact of its declared kind.")


__all__ = ["Confidence", "Evidence", "FactAttribution", "SourceLocation"]
