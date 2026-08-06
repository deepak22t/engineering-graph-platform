"""Schemas for evidence creation requests and response payloads."""

from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, Field

from packages.domain.enums import ExtractionMethod
from packages.domain.evidence import Evidence, SourceLocation


class CreateEvidenceRequest(BaseModel):
    """Payload schema for submitting a new evidence record."""

    source_artifact_id: UUID
    line_number: int | None = None
    page_number: int | None = None
    json_path: str | None = None
    xpath: str | None = None
    byte_offset: int | None = None
    bounding_box: dict[str, float] | None = None
    section: str | None = None
    extraction_method: ExtractionMethod
    extractor_version: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_reference: str | None = None
    notes: str | None = None

    def to_evidence(self) -> Evidence:
        """Convert payload to a canonical Evidence instance."""
        location = SourceLocation(
            line_number=self.line_number,
            page_number=self.page_number,
            json_path=self.json_path,
            xpath=self.xpath,
            byte_offset=self.byte_offset,
            bounding_box=self.bounding_box,
            section=self.section,
        )
        return Evidence(
            source_artifact_id=self.source_artifact_id,
            source_location=location,
            extraction_method=self.extraction_method,
            extractor_version=self.extractor_version,
            confidence=self.confidence,
            observed_at=datetime.now(timezone.utc),
            evidence_reference=self.evidence_reference,
            notes=self.notes,
        )


class EvidenceResponse(BaseModel):
    """API response payload schema for an evidence record."""

    source_artifact_id: UUID
    source_location: SourceLocation
    extraction_method: ExtractionMethod
    extractor_version: str
    confidence: float
    observed_at: datetime
    evidence_reference: str | None
    notes: str | None

    @classmethod
    def from_evidence(cls, evidence: Evidence) -> "EvidenceResponse":
        """Construct response schema from a canonical Evidence instance."""
        return cls(
            source_artifact_id=evidence.source_artifact_id,
            source_location=evidence.source_location,
            extraction_method=evidence.extraction_method,
            extractor_version=evidence.extractor_version,
            confidence=evidence.confidence,
            observed_at=evidence.observed_at,
            evidence_reference=evidence.evidence_reference,
            notes=evidence.notes,
        )
