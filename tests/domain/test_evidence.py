"""Tests for Evidence, SourceLocation, Confidence, and evidence schemas."""

from datetime import datetime, timezone
import uuid

from pydantic import ValidationError
import pytest

from packages.domain.enums import ConfidenceLevel, ExtractionMethod
from packages.domain.evidence import Confidence, Evidence, SourceLocation
from packages.schemas.domain.evidence_schema import CreateEvidenceRequest, EvidenceResponse


def test_create_valid_source_location():
    loc_empty = SourceLocation()
    assert loc_empty.line_number is None
    assert loc_empty.json_path is None

    loc_full = SourceLocation(
        line_number=42,
        page_number=3,
        json_path="$.devices[0]",
        xpath="//device[1]",
        byte_offset=1024,
        bounding_box={"x": 10.0, "y": 20.0, "w": 100.0, "h": 50.0},
        section="Core Interfaces",
    )
    assert loc_full.line_number == 42
    assert loc_full.section == "Core Interfaces"


def test_create_valid_evidence():
    art_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    ev = Evidence(
        source_artifact_id=art_id,
        source_location=SourceLocation(line_number=10),
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1.0.0",
        confidence=0.95,
        observed_at=now,
        evidence_reference="hostname router-01",
        notes="extracted from cisco config",
    )

    assert ev.source_artifact_id == art_id
    assert ev.confidence == 0.95
    assert ev.extraction_method == ExtractionMethod.DETERMINISTIC_PARSER
    assert ev.observed_at == now


def test_confidence_validation_bounds():
    art_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Valid boundary: 0.0
    ev_zero = Evidence(
        source_artifact_id=art_id,
        extraction_method=ExtractionMethod.LLM,
        extractor_version="1.0",
        confidence=0.0,
        observed_at=now,
    )
    assert ev_zero.confidence == 0.0

    # Valid boundary: 1.0
    ev_one = Evidence(
        source_artifact_id=art_id,
        extraction_method=ExtractionMethod.LLM,
        extractor_version="1.0",
        confidence=1.0,
        observed_at=now,
    )
    assert ev_one.confidence == 1.0

    # Invalid: < 0.0
    with pytest.raises(ValidationError):
        Evidence(
            source_artifact_id=art_id,
            extraction_method=ExtractionMethod.LLM,
            extractor_version="1.0",
            confidence=-0.1,
            observed_at=now,
        )

    # Invalid: > 1.0
    with pytest.raises(ValidationError):
        Evidence(
            source_artifact_id=art_id,
            extraction_method=ExtractionMethod.LLM,
            extractor_version="1.0",
            confidence=1.01,
            observed_at=now,
        )


def test_confidence_from_score_levels():
    conf_high = Confidence.from_score(0.90)
    assert conf_high.level == ConfidenceLevel.HIGH

    conf_high_boundary = Confidence.from_score(0.85)
    assert conf_high_boundary.level == ConfidenceLevel.HIGH

    conf_med = Confidence.from_score(0.70)
    assert conf_med.level == ConfidenceLevel.MEDIUM

    conf_med_boundary = Confidence.from_score(0.60)
    assert conf_med_boundary.level == ConfidenceLevel.MEDIUM

    conf_low = Confidence.from_score(0.40)
    assert conf_low.level == ConfidenceLevel.LOW

    conf_zero = Confidence.from_score(0.00)
    assert conf_zero.level == ConfidenceLevel.LOW


def test_create_evidence_request_schema():
    art_id = uuid.uuid4()

    req = CreateEvidenceRequest(
        source_artifact_id=art_id,
        line_number=25,
        section="bgp_config",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="2.0.0",
        confidence=0.89,
        evidence_reference="router bgp 65000",
    )

    ev = req.to_evidence()

    assert ev.source_artifact_id == art_id
    assert ev.source_location.line_number == 25
    assert ev.source_location.section == "bgp_config"
    assert ev.confidence == 0.89
    assert ev.extraction_method == ExtractionMethod.DETERMINISTIC_PARSER


def test_evidence_response_schema():
    art_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    ev = Evidence(
        source_artifact_id=art_id,
        source_location=SourceLocation(line_number=10),
        extraction_method=ExtractionMethod.OCR,
        extractor_version="1.1.0",
        confidence=0.75,
        observed_at=now,
    )

    resp = EvidenceResponse.from_evidence(ev)

    assert resp.source_artifact_id == art_id
    assert resp.source_location.line_number == 10
    assert resp.extraction_method == ExtractionMethod.OCR
    assert resp.confidence == 0.75
    assert resp.observed_at == now
