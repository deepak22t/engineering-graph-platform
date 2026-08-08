"""Safe API schemas for precise evidence records."""

from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from packages.domain.enums import ExtractionMethod
from packages.domain.evidence import Evidence, SourceLocation


class CreateEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_artifact_id: UUID
    source_artifact_version: str | None = None
    source_artifact_checksum: str | None = None
    source_location: SourceLocation = Field(default_factory=SourceLocation)
    evidence_reference: str | None = None
    extracted_value: str | None = None
    extraction_method: ExtractionMethod
    extractor_version: str
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str | None = None

    def to_evidence(self) -> Evidence:
        now = datetime.now(timezone.utc)
        return Evidence(
            source_artifact_id=self.source_artifact_id,
            source_artifact_version=self.source_artifact_version,
            source_artifact_checksum=self.source_artifact_checksum,
            source_location=self.source_location,
            evidence_reference=self.evidence_reference,
            extracted_value=self.extracted_value,
            extraction_method=self.extraction_method,
            extractor_version=self.extractor_version,
            observed_at=now,
            recorded_at=now,
            confidence=self.confidence,
            notes=self.notes,
        )


class EvidenceResponse(BaseModel):
    id: UUID
    source_artifact_id: UUID
    source_artifact_version: str | None
    source_artifact_checksum: str | None
    source_location: SourceLocation
    evidence_reference: str | None
    extracted_value: str | None
    extraction_method: ExtractionMethod
    extractor_version: str
    observed_at: datetime
    recorded_at: datetime
    confidence: float
    notes: str | None

    @classmethod
    def from_evidence(cls, evidence: Evidence) -> "EvidenceResponse":
        return cls.model_validate(evidence.model_dump())
