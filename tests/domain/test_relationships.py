"""Tests for relationship models and API schemas."""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from packages.domain.enums import ExtractionMethod, RelationshipType
from packages.domain.evidence import Confidence, Evidence, SourceLocation
from packages.domain.ids import generate_relationship_id
from packages.domain.relationships import EvidenceBackedRelationship, Relationship
from packages.schemas.domain.relationship_schema import (
    CreateRelationshipRequest,
    RelationshipResponse,
)


def relationship(kind=RelationshipType.CONNECTED_TO):
    now = datetime.now(timezone.utc)
    source_id, target_id = uuid.uuid4(), uuid.uuid4()
    return Relationship(
        id=generate_relationship_id(kind, source_id, target_id),
        relationship_type=kind,
        source_id=source_id,
        target_id=target_id,
        created_at=now,
        updated_at=now,
    )


def test_relationship_is_immutable():
    value = relationship()
    with pytest.raises((ValidationError, TypeError)):
        value.relationship_type = RelationshipType.HAS_INTERFACE


def test_connected_to_request_uses_sorted_canonical_endpoints():
    source_id, target_id = uuid.uuid4(), uuid.uuid4()
    result = CreateRelationshipRequest(
        relationship_type=RelationshipType.CONNECTED_TO, source_id=source_id, target_id=target_id
    ).to_relationship()
    expected_source, expected_target = sorted((source_id, target_id), key=str)
    assert (result.source_id, result.target_id) == (expected_source, expected_target)
    assert result.id == generate_relationship_id(
        RelationshipType.CONNECTED_TO, expected_source, expected_target
    )


def test_directed_request_preserves_endpoint_order():
    source_id, target_id = uuid.uuid4(), uuid.uuid4()
    result = CreateRelationshipRequest(
        relationship_type=RelationshipType.HAS_INTERFACE, source_id=source_id, target_id=target_id
    ).to_relationship()
    assert (result.source_id, result.target_id) == (source_id, target_id)


def test_relationship_response_and_evidence_wrapper():
    value = relationship()
    response = RelationshipResponse.from_relationship(value)
    evidence = Evidence(
        source_artifact_id=uuid.uuid4(),
        source_location=SourceLocation(line_start=1),
        extraction_method=ExtractionMethod.HUMAN,
        extractor_version="1",
        confidence=0.9,
        observed_at=datetime.now(timezone.utc),
    )
    wrapped = EvidenceBackedRelationship(
        relationship=value, evidence=[evidence], confidence=Confidence.from_score(0.9)
    )
    assert response.id == value.id
    assert wrapped.id == value.id
    with pytest.raises(ValidationError):
        EvidenceBackedRelationship(
            relationship=value, evidence=[], confidence=Confidence.from_score(0.9)
        )
