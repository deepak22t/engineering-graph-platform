"""Tests for engineering scope on typed canonical entities."""

import uuid

from packages.domain.entities import DeviceEntity, DeviceProperties
from packages.domain.identity import DeviceIdentity
from packages.domain.scope import GraphScope


def make_entity(environment: str, site_id: int) -> DeviceEntity:
    scope = GraphScope(
        organization_id=uuid.UUID(int=10),
        project_id=uuid.UUID(int=20),
        environment=environment,
        site_id=uuid.UUID(int=site_id),
    )
    return DeviceEntity(
        identity=DeviceIdentity(scope=scope, hostname="router-01"),
        display_name="router-01",
        properties=DeviceProperties(hostname="router-01"),
        first_observed_at="2026-08-07T00:00:00Z",
        last_observed_at="2026-08-07T00:00:00Z",
        created_at="2026-08-07T00:00:00Z",
        updated_at="2026-08-07T00:00:00Z",
    )


def test_same_name_in_different_scopes_has_distinct_canonical_identities():
    entities = (make_entity("prod", 1), make_entity("dev", 1), make_entity("prod", 2))
    assert len({entity.id for entity in entities}) == 3
