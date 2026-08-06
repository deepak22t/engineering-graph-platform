"""Tests for Entity, EvidenceBackedEntity, and entity schemas."""

from datetime import datetime, timezone
import uuid

from pydantic import ValidationError
import pytest

from packages.domain.entities import Entity, EvidenceBackedEntity
from packages.domain.enums import EntityType, ExtractionMethod
from packages.domain.evidence import Confidence, Evidence, SourceLocation
from packages.domain.ids import generate_entity_id
from packages.schemas.domain.entity_schema import CreateEntityRequest, EntityResponse


@pytest.fixture
def sample_timestamps():
    now = datetime.now(timezone.utc)
    return now, now


@pytest.fixture
def sample_evidence():
    return Evidence(
        source_artifact_id=uuid.uuid4(),
        source_location=SourceLocation(line_number=10),
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1.0.0",
        confidence=0.95,
        observed_at=datetime.now(timezone.utc),
    )


def test_create_valid_entity(sample_timestamps):
    created_at, updated_at = sample_timestamps
    entity_id = generate_entity_id(EntityType.DEVICE, "router-01")

    entity = Entity(
        id=entity_id,
        entity_type=EntityType.DEVICE,
        name="router-01",
        attributes={"vendor": "Cisco", "model": "ISR4451"},
        tags=["core", "datacenter"],
        created_at=created_at,
        updated_at=updated_at,
    )

    assert entity.id == entity_id
    assert entity.entity_type == EntityType.DEVICE
    assert entity.name == "router-01"
    assert entity.attributes == {"vendor": "Cisco", "model": "ISR4451"}
    assert entity.tags == ["core", "datacenter"]


def test_entity_empty_name_validation(sample_timestamps):
    created_at, updated_at = sample_timestamps
    entity_id = generate_entity_id(EntityType.DEVICE, "router-01")

    with pytest.raises(ValidationError):
        Entity(
            id=entity_id,
            entity_type=EntityType.DEVICE,
            name="",  # Empty name not allowed
            created_at=created_at,
            updated_at=updated_at,
        )


def test_all_entity_types_valid(sample_timestamps):
    created_at, updated_at = sample_timestamps

    for entity_type in EntityType:
        entity_id = generate_entity_id(entity_type, f"test-{entity_type.value}")
        entity = Entity(
            id=entity_id,
            entity_type=entity_type,
            name=f"test-{entity_type.value}",
            created_at=created_at,
            updated_at=updated_at,
        )
        assert entity.entity_type == entity_type


def test_entity_immutability(sample_timestamps):
    created_at, updated_at = sample_timestamps
    entity_id = generate_entity_id(EntityType.DEVICE, "router-01")

    entity = Entity(
        id=entity_id,
        entity_type=EntityType.DEVICE,
        name="router-01",
        created_at=created_at,
        updated_at=updated_at,
    )

    with pytest.raises((ValidationError, TypeError)):
        entity.name = "new-name"  # Frozen instance cannot be mutated


def test_create_entity_request_schema():
    req = CreateEntityRequest(
        entity_type=EntityType.DEVICE,
        name="  switch-core-01  ",
        attributes={"vendor": "Arista"},
        tags=["edge"],
    )

    entity = req.to_entity()

    assert entity.name == "switch-core-01"  # Whitespace stripped
    assert entity.id == generate_entity_id(EntityType.DEVICE, "switch-core-01")
    assert entity.attributes == {"vendor": "Arista"}
    assert entity.tags == ["edge"]


def test_entity_response_schema(sample_timestamps):
    created_at, updated_at = sample_timestamps
    entity_id = generate_entity_id(EntityType.DEVICE, "router-01")

    entity = Entity(
        id=entity_id,
        entity_type=EntityType.DEVICE,
        name="router-01",
        attributes={"vendor": "Cisco"},
        tags=["core"],
        created_at=created_at,
        updated_at=updated_at,
    )

    response = EntityResponse.from_entity(entity)

    assert response.id == entity.id
    assert response.entity_type == entity.entity_type
    assert response.name == entity.name
    assert response.attributes == entity.attributes
    assert response.tags == entity.tags


def test_evidence_backed_entity_valid(sample_timestamps, sample_evidence):
    created_at, updated_at = sample_timestamps
    entity_id = generate_entity_id(EntityType.DEVICE, "router-01")

    entity = Entity(
        id=entity_id,
        entity_type=EntityType.DEVICE,
        name="router-01",
        created_at=created_at,
        updated_at=updated_at,
    )

    conf = Confidence.from_score(0.95)
    eb_entity = EvidenceBackedEntity(
        entity=entity,
        evidence=[sample_evidence],
        confidence=conf,
    )

    assert eb_entity.id == entity_id
    assert eb_entity.entity_type == EntityType.DEVICE
    assert len(eb_entity.evidence) == 1
    assert eb_entity.confidence.score == 0.95


def test_evidence_backed_entity_requires_evidence(sample_timestamps):
    created_at, updated_at = sample_timestamps
    entity_id = generate_entity_id(EntityType.DEVICE, "router-01")

    entity = Entity(
        id=entity_id,
        entity_type=EntityType.DEVICE,
        name="router-01",
        created_at=created_at,
        updated_at=updated_at,
    )

    conf = Confidence.from_score(0.95)

    with pytest.raises(ValidationError):
        EvidenceBackedEntity(
            entity=entity,
            evidence=[],  # Empty list must raise ValidationError
            confidence=conf,
        )
