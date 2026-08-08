"""Tests for lifecycle and observation semantics."""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from packages.domain.entities import (
    DeviceEntity,
    DeviceProperties,
    LifecycleState,
    ObservationState,
)
from packages.domain.enums import ExtractionMethod
from packages.domain.evidence import Evidence, SourceLocation
from packages.domain.identity import DeviceIdentity
from packages.domain.scope import GraphScope


def test_lifecycle_and_observation_states_are_separate_and_non_destructive():
    now = datetime.now(timezone.utc)
    scope = GraphScope(
        organization_id=uuid.UUID(int=1),
        project_id=uuid.UUID(int=2),
        environment="prod",
        site_id=uuid.UUID(int=3),
    )
    entity = DeviceEntity(
        identity=DeviceIdentity(scope=scope, hostname="router"),
        display_name="router",
        properties=DeviceProperties(hostname="router"),
        lifecycle_state=LifecycleState.UNKNOWN,
        first_observed_at=now,
        last_observed_at=now,
        valid_from=now,
        created_at=now,
        updated_at=now,
    )
    evidence = Evidence(
        source_artifact_id=uuid.uuid4(),
        source_location=SourceLocation(line_start=1),
        extraction_method=ExtractionMethod.HUMAN,
        extractor_version="1",
        observed_at=now,
        observation_state=ObservationState.NOT_OBSERVED,
        confidence=0.9,
    )
    assert entity.lifecycle_state == LifecycleState.UNKNOWN
    assert evidence.observation_state == ObservationState.NOT_OBSERVED


def test_validity_range_is_auditable_and_validated():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        DeviceEntity(
            identity=DeviceIdentity(
                scope=GraphScope(
                    organization_id=uuid.UUID(int=1),
                    project_id=uuid.UUID(int=2),
                    environment="prod",
                    site_id=uuid.UUID(int=3),
                ),
                hostname="router",
            ),
            display_name="router",
            properties=DeviceProperties(hostname="router"),
            first_observed_at=now,
            last_observed_at=now,
            valid_from=now,
            valid_to=now.replace(year=2025),
            created_at=now,
            updated_at=now,
        )
