"""Tests for typed canonical entities and safe entity schemas."""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from packages.domain.entities import DeviceEntity, DeviceProperties, EvidenceBackedEntity
from packages.domain.enums import ExtractionMethod
from packages.domain.evidence import Confidence, Evidence, SourceLocation
from packages.domain.identity import DeviceIdentity
from packages.domain.scope import GraphScope
from packages.schemas.domain.entity_schema import CreateEntityRequest, EntityResponse

SCOPE = GraphScope(
    organization_id=uuid.UUID(int=1),
    project_id=uuid.UUID(int=2),
    environment="prod",
    site_id=uuid.UUID(int=3),
)


def device_identity() -> DeviceIdentity:
    return DeviceIdentity(scope=SCOPE, hostname="router-01")


def device_entity(name: str = "Router 01") -> DeviceEntity:
    now = datetime.now(timezone.utc)
    return DeviceEntity(
        identity=device_identity(),
        display_name=name,
        properties=DeviceProperties(hostname="router-01", vendor="Cisco"),
        first_observed_at=now,
        last_observed_at=now,
        created_at=now,
        updated_at=now,
    )


def test_device_entity_is_typed_and_scope_aware():
    entity = device_entity()
    assert entity.properties.vendor == "cisco"
    assert entity.entity_type.value == "DEVICE"
    assert entity.scope == SCOPE


def test_typed_entity_rejects_unknown_properties_and_naive_timestamps():
    with pytest.raises(ValidationError):
        DeviceProperties(hostname="router-01", unsupported="value")
    with pytest.raises(ValidationError):
        DeviceEntity(
            identity=device_identity(),
            display_name="router",
            properties=DeviceProperties(hostname="router-01"),
            first_observed_at=datetime.now(),
            last_observed_at=datetime.now(),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )


def test_api_request_validates_identity_property_type_and_serializes():
    request = CreateEntityRequest(
        identity=device_identity(),
        display_name=" Core Router ",
        properties=DeviceProperties(hostname="router-01", management_ip="10.0.0.1"),
    )
    entity = request.to_entity()
    response = EntityResponse.from_entity(entity)
    assert entity.display_name == "Core Router"
    assert response.properties.management_ip == "10.0.0.1"
    assert response.identity == entity.identity


def test_entity_rejects_arbitrary_id_and_is_immutable():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        DeviceEntity(
            id=uuid.uuid4(),
            identity=device_identity(),
            display_name="router",
            properties=DeviceProperties(hostname="router-01"),
            first_observed_at=now,
            last_observed_at=now,
            created_at=now,
            updated_at=now,
        )
    entity = device_entity()
    with pytest.raises((ValidationError, TypeError)):
        entity.properties = DeviceProperties(hostname="router-02")


def test_evidence_backed_typed_entity_requires_evidence():
    evidence = Evidence(
        source_artifact_id=uuid.uuid4(),
        source_location=SourceLocation(line_start=10),
        extraction_method=ExtractionMethod.HUMAN,
        extractor_version="1",
        confidence=0.9,
        observed_at=datetime.now(timezone.utc),
    )
    backed = EvidenceBackedEntity(
        entity=device_entity(), evidence=[evidence], confidence=Confidence.from_score(0.9)
    )
    assert backed.id == backed.entity.id
    with pytest.raises(ValidationError):
        EvidenceBackedEntity(
            entity=device_entity(), evidence=[], confidence=Confidence.from_score(0.9)
        )
