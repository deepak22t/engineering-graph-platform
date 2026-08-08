"""Single deterministic confidence policy for canonical facts."""

from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field, computed_field

from packages.domain.enums import ConfidenceLevel, ExtractionMethod

POLICY_VERSION = "1"
_METHOD_WEIGHT = {
    ExtractionMethod.HUMAN: 1.0,
    ExtractionMethod.DETERMINISTIC_PARSER: 0.95,
    ExtractionMethod.OCR: 0.70,
    ExtractionMethod.LLM: 0.65,
    ExtractionMethod.VLM: 0.65,
    ExtractionMethod.INFERRED: 0.50,
}


class Confidence(BaseModel):
    """Score with level derived exclusively from the shared policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    score: float = Field(ge=0.0, le=1.0)
    method: str
    rationale: str | None = None
    policy_version: str = POLICY_VERSION

    @computed_field
    @property
    def level(self) -> ConfidenceLevel:
        return ConfidenceLevel.from_score(self.score)

    @computed_field
    @property
    def auto_commit_eligible(self) -> bool:
        return self.score >= 0.85 and self.method in {
            "aggregate",
            "deterministic_parser",
            "human_confirmed",
        }

    @classmethod
    def from_score(
        cls, score: float, method: str = "aggregate", reasoning: str | None = None
    ) -> "Confidence":
        return cls(score=score, method=method, rationale=reasoning)


def aggregate_confidence(evidence_records: Iterable) -> Confidence:
    """Aggregate evidence deterministically with method weights and conflict penalty."""
    records = sorted(tuple(evidence_records), key=lambda item: str(item.id))
    if not records:
        raise ValueError("At least one evidence record is required.")
    weighted = [record.confidence * _METHOD_WEIGHT[record.extraction_method] for record in records]
    score = sum(weighted) / len(weighted)
    values = [record.extracted_value for record in records if record.extracted_value is not None]
    distinct = len(set(values))
    if distinct > 1:
        score *= 0.70
        rationale = "contradictory extracted values reduced confidence"
    else:
        score = min(1.0, score + min(0.05 * (len(records) - 1), 0.10))
        rationale = "agreeing evidence increased confidence"
    if any(record.extraction_method == ExtractionMethod.HUMAN for record in records):
        score = max(score, 0.95)
        rationale = "human-confirmed evidence applied"
    return Confidence(score=round(score, 6), method="aggregate", rationale=rationale)
