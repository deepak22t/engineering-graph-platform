"""Tests for precise evidence and fact-level attribution."""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from packages.domain.enums import ExtractionMethod
from packages.domain.evidence import Evidence, FactAttribution, SourceLocation


def evidence(location=None, **kwargs):
    return Evidence(
        source_artifact_id=uuid.uuid4(),
        source_location=location or SourceLocation(line_start=1),
        extraction_method=ExtractionMethod.HUMAN,
        extractor_version="1",
        observed_at=datetime.now(timezone.utc),
        confidence=0.9,
        **kwargs,
    )


def test_precise_locations_validate_ranges_and_coordinates():
    assert SourceLocation(line_start=2, line_end=3, page_number=1).is_precise
    with pytest.raises(ValidationError):
        SourceLocation(line_start=3, line_end=2)
    with pytest.raises(ValidationError):
        SourceLocation(page_number=0)
    with pytest.raises(ValidationError):
        SourceLocation(bounding_box=(0, -1, 2, 3))


def test_evidence_requires_locator_or_reference():
    with pytest.raises(ValidationError):
        evidence(location=SourceLocation())
    assert (
        evidence(location=SourceLocation(), evidence_reference="review-42").evidence_reference
        == "review-42"
    )


def test_property_and_relationship_attribution_are_separate():
    record = evidence()
    property_link = FactAttribution(
        evidence_id=record.id,
        fact_kind="property",
        entity_id=uuid.uuid4(),
        property_path="properties.hostname",
    )
    relationship_link = FactAttribution(
        evidence_id=record.id, fact_kind="relationship", relationship_id=uuid.uuid4()
    )
    assert property_link.property_path == "properties.hostname"
    assert relationship_link.relationship_id is not None
    with pytest.raises(ValidationError):
        FactAttribution(evidence_id=record.id, fact_kind="property", entity_id=uuid.uuid4())


def test_evidence_does_not_invent_an_observation_time() -> None:
    record = Evidence(
        source_artifact_id=uuid.uuid4(),
        source_location=SourceLocation(line_start=1),
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        confidence=0.9,
    )

    assert record.observed_at is None
    assert record.recorded_at.tzinfo is not None
