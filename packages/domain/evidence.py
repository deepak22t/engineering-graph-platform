"""Provenance and evidence models for the canonical engineering graph.

Every fact extracted into the graph carries an evidence record linking it back to
its source artifact, exact location within the artifact, extraction method, and
confidence score.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from packages.domain.enums import ConfidenceLevel, ExtractionMethod


class SourceLocation(BaseModel):
    """Specific location within a source artifact where a fact was found."""

    line_number: int | None = None
    page_number: int | None = None
    json_path: str | None = None
    xpath: str | None = None
    byte_offset: int | None = None
    bounding_box: dict[str, float] | None = None
    section: str | None = None


class Evidence(BaseModel):
    """Provenance record tracking the origin and confidence of an extracted fact."""

    source_artifact_id: UUID
    source_location: SourceLocation = Field(default_factory=SourceLocation)
    extraction_method: ExtractionMethod
    extractor_version: str
    confidence: float = Field(ge=0.0, le=1.0)
    observed_at: datetime
    evidence_reference: str | None = None
    notes: str | None = None


class Confidence(BaseModel):
    """Confidence score and qualitative assessment for a graph fact."""

    score: float = Field(ge=0.0, le=1.0)
    level: ConfidenceLevel
    method: str
    reasoning: str | None = None

    @classmethod
    def from_score(
        cls, score: float, method: str = "default", reasoning: str | None = None
    ) -> "Confidence":
        """Create a Confidence instance deriving the level automatically from the score."""
        return cls(
            score=score,
            level=ConfidenceLevel.from_score(score),
            method=method,
            reasoning=reasoning,
        )
