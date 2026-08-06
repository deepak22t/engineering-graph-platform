"""Tests for Relationship, EvidenceBackedRelationship, and relationship schemas."""

from datetime import datetime, timezone
import uuid

from pydantic import ValidationError
import pytest

from packages.domain.enums import EntityType, ExtractionMethod, RelationshipType
from packages.domain.evidence import Confidence, Evidence, SourceLocation
from packages.domain.ids import generate_entity_id, generate_relationship_id
from packages.domain.relationships import EvidenceBackedRelationship, Relationship
from packages.schemas.domain.relationship_schema import (
    CreateRelationshipRequest,
    RelationshipResponse,
)


@pytest.fixture
def sample_timestamps():
    now = datetime.now(timezone.utc)
    return now, now


@pytest.fixture
def sample_evidence():
    return Evidence(
        source_artifact_id=uuid.uuid4(),
        source_location=SourceLocation(line_number=5),
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1.0.0",
        confidence=0.90,
        observed_at=datetime.now(timezone.utc),
    )


def test_create_valid_relationship(sample_timestamps):
    created_at, updated_at = sample_timestamps
    src_id = generate_entity_id(EntityType.DEVICE, "router-01")
    tgt_id = generate_entity_id(EntityType.INTERFACE, "eth0")
    rel_id = generate_relationship_id(RelationshipType.HAS_INTERFACE, src_id, tgt_id)

    rel = Relationship(
        id=rel_id,
        relationship_type=RelationshipType.HAS_INTERFACE,
        source_id=src_id,
        target_id=tgt_id,
        attributes={"speed": "1Gbps"},
        created_at=created_at,
        updated_at=updated_at,
    )

    assert rel.id == rel_id
    assert rel.relationship_type == RelationshipType.HAS_INTERFACE
    assert rel.source_id == src_id
    assert rel.target_id == tgt_id
    assert rel.attributes == {"speed": "1Gbps"}


def test_relationship_self_loop_validation(sample_timestamps):
    created_at, updated_at = sample_timestamps
    src_id = generate_entity_id(EntityType.DEVICE, "router-01")
    rel_id = generate_relationship_id(RelationshipType.CONNECTED_TO, src_id, src_id)

    with pytest.raises(ValidationError):
        Relationship(
            id=rel_id,
            relationship_type=RelationshipType.CONNECTED_TO,
            source_id=src_id,
            target_id=src_id,  # Self-loop forbidden!
            created_at=created_at,
            updated_at=updated_at,
        )


def test_all_relationship_types_valid(sample_timestamps):
    created_at, updated_at = sample_timestamps
    src_id = uuid.uuid4()
    tgt_id = uuid.uuid4()

    for rel_type in RelationshipType:
        rel_id = generate_relationship_id(rel_type, src_id, tgt_id)
        rel = Relationship(
            id=rel_id,
            relationship_type=rel_type,
            source_id=src_id,
            target_id=tgt_id,
            created_at=created_at,
            updated_at=updated_at,
        )
        assert rel.relationship_type == rel_type


def test_relationship_immutability(sample_timestamps):
    created_at, updated_at = sample_timestamps
    src_id = uuid.uuid4()
    tgt_id = uuid.uuid4()
    rel_id = generate_relationship_id(RelationshipType.CONNECTED_TO, src_id, tgt_id)

    rel = Relationship(
        id=rel_id,
        relationship_type=RelationshipType.CONNECTED_TO,
        source_id=src_id,
        target_id=tgt_id,
        created_at=created_at,
        updated_at=updated_at,
    )

    with pytest.raises((ValidationError, TypeError)):
        rel.relationship_type = RelationshipType.HAS_INTERFACE  # Frozen model cannot mutate


def test_create_relationship_request_schema():
    src_id = uuid.uuid4()
    tgt_id = uuid.uuid4()

    req = CreateRelationshipRequest(
        relationship_type=RelationshipType.CONNECTED_TO,
        source_id=src_id,
        target_id=tgt_id,
        attributes={"duplex": "full"},
    )

    rel = req.to_relationship()

    assert rel.relationship_type == RelationshipType.CONNECTED_TO
    assert rel.source_id == src_id
    assert rel.target_id == tgt_id
    assert rel.attributes == {"duplex": "full"}
    assert rel.id == generate_relationship_id(RelationshipType.CONNECTED_TO, src_id, tgt_id)


def test_create_relationship_request_self_loop_validation():
    same_id = uuid.uuid4()

    with pytest.raises(ValidationError):
        CreateRelationshipRequest(
            relationship_type=RelationshipType.CONNECTED_TO,
            source_id=same_id,
            target_id=same_id,
        )


def test_relationship_response_schema(sample_timestamps):
    created_at, updated_at = sample_timestamps
    src_id = uuid.uuid4()
    tgt_id = uuid.uuid4()
    rel_id = generate_relationship_id(RelationshipType.CONNECTED_TO, src_id, tgt_id)

    rel = Relationship(
        id=rel_id,
        relationship_type=RelationshipType.CONNECTED_TO,
        source_id=src_id,
        target_id=tgt_id,
        attributes={"medium": "fiber"},
        created_at=created_at,
        updated_at=updated_at,
    )

    response = RelationshipResponse.from_relationship(rel)

    assert response.id == rel.id
    assert response.relationship_type == rel.relationship_type
    assert response.source_id == rel.source_id
    assert response.target_id == rel.target_id
    assert response.attributes == rel.attributes


def test_evidence_backed_relationship_valid(sample_timestamps, sample_evidence):
    created_at, updated_at = sample_timestamps
    src_id = uuid.uuid4()
    tgt_id = uuid.uuid4()
    rel_id = generate_relationship_id(RelationshipType.CONNECTED_TO, src_id, tgt_id)

    rel = Relationship(
        id=rel_id,
        relationship_type=RelationshipType.CONNECTED_TO,
        source_id=src_id,
        target_id=tgt_id,
        created_at=created_at,
        updated_at=updated_at,
    )

    conf = Confidence.from_score(0.90)
    eb_rel = EvidenceBackedRelationship(
        relationship=rel,
        evidence=[sample_evidence],
        confidence=conf,
    )

    assert eb_rel.id == rel_id
    assert eb_rel.relationship_type == RelationshipType.CONNECTED_TO
    assert len(eb_rel.evidence) == 1
    assert eb_rel.confidence.score == 0.90


def test_evidence_backed_relationship_requires_evidence(sample_timestamps):
    created_at, updated_at = sample_timestamps
    src_id = uuid.uuid4()
    tgt_id = uuid.uuid4()
    rel_id = generate_relationship_id(RelationshipType.CONNECTED_TO, src_id, tgt_id)

    rel = Relationship(
        id=rel_id,
        relationship_type=RelationshipType.CONNECTED_TO,
        source_id=src_id,
        target_id=tgt_id,
        created_at=created_at,
        updated_at=updated_at,
    )

    conf = Confidence.from_score(0.90)

    with pytest.raises(ValidationError):
        EvidenceBackedRelationship(
            relationship=rel,
            evidence=[],  # Empty list must raise ValidationError
            confidence=conf,
        )
