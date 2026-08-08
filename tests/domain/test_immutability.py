"""Tests for deep canonical-fact immutability."""

import uuid
from datetime import datetime, timezone

import pytest

from packages.domain.entities import DeviceProperties
from packages.domain.enums import ExtractionMethod, RelationshipType
from packages.domain.evidence import Evidence, SourceLocation
from packages.domain.identity import DeviceIdentity
from packages.domain.relationships import Relationship
from packages.domain.scope import GraphScope


def test_nested_extensions_and_relationship_attributes_cannot_mutate():
    properties = DeviceProperties(hostname="router", extensions={"nested": {"values": [1]}})
    with pytest.raises(TypeError):
        properties.extensions["new"] = 1
    with pytest.raises(TypeError):
        properties.extensions["nested"]["new"] = 1
    now = datetime.now(timezone.utc)
    relationship = Relationship(
        id=uuid.uuid4(),
        relationship_type=RelationshipType.CONNECTED_TO,
        source_id=uuid.uuid4(),
        target_id=uuid.uuid4(),
        attributes={"nested": {"values": [1]}},
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(TypeError):
        relationship.attributes["new"] = 1
    with pytest.raises(TypeError):
        relationship.attributes["nested"]["new"] = 1


def test_evidence_record_is_immutable():
    record = Evidence(
        source_artifact_id=uuid.uuid4(),
        source_location=SourceLocation(line_start=1),
        extraction_method=ExtractionMethod.HUMAN,
        extractor_version="1",
        observed_at=datetime.now(timezone.utc),
        confidence=0.9,
    )
    with pytest.raises((TypeError, ValueError)):
        record.notes = "changed after creation"
    with pytest.raises((TypeError, ValueError)):
        record.source_location.line_start = 2


def test_identity_cannot_change_after_creation():
    identity = DeviceIdentity(
        scope=GraphScope(
            organization_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            environment="prod",
            site_id=uuid.uuid4(),
        ),
        hostname="router-01",
    )
    with pytest.raises((TypeError, ValueError)):
        identity.hostname = "router-02"

    returned_fields = identity.identity_fields
    returned_fields["hostname"] = "router-02"
    assert identity.identity_fields["hostname"] == "router-01"
