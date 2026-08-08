"""Tests for the shared confidence policy."""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from packages.domain.confidence import Confidence, aggregate_confidence
from packages.domain.enums import ConfidenceLevel, ExtractionMethod
from packages.domain.evidence import Evidence, SourceLocation


def evidence(score, method, value="router-01"):
    return Evidence(
        id=uuid.uuid4(),
        source_artifact_id=uuid.uuid4(),
        source_location=SourceLocation(line_start=1),
        extracted_value=value,
        extraction_method=method,
        extractor_version="1",
        observed_at=datetime.now(timezone.utc),
        confidence=score,
    )


def test_level_is_derived_and_cannot_conflict_with_score():
    confidence = Confidence(score=0.10, method="aggregate")
    assert confidence.level == ConfidenceLevel.LOW
    with pytest.raises(ValidationError):
        Confidence(score=0.10, level=ConfidenceLevel.HIGH, method="aggregate")


def test_threshold_boundaries_and_auto_commit_policy():
    assert Confidence(score=0.85, method="aggregate").level == ConfidenceLevel.HIGH
    assert Confidence(score=0.849, method="aggregate").level == ConfidenceLevel.MEDIUM
    assert Confidence(score=0.599, method="aggregate").level == ConfidenceLevel.LOW
    assert Confidence(score=0.95, method="llm").auto_commit_eligible is False
    assert Confidence(score=0.95, method="aggregate").auto_commit_eligible is True


def test_aggregation_is_deterministic_and_handles_agreement_conflict_and_human():
    first, second = (
        evidence(0.8, ExtractionMethod.DETERMINISTIC_PARSER),
        evidence(0.8, ExtractionMethod.LLM),
    )
    assert aggregate_confidence([first, second]) == aggregate_confidence([second, first])
    conflict = aggregate_confidence(
        [first, evidence(0.8, ExtractionMethod.DETERMINISTIC_PARSER, "router-02")]
    )
    assert conflict.score < aggregate_confidence([first, second]).score
    human = aggregate_confidence([evidence(0.1, ExtractionMethod.HUMAN)])
    assert human.score >= 0.95 and human.rationale == "human-confirmed evidence applied"


def test_empty_evidence_cannot_aggregate():
    with pytest.raises(ValueError):
        aggregate_confidence([])
