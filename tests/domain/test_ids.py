"""Tests for canonical entity and relationship identifiers."""

import uuid

from packages.domain.enums import RelationshipType
from packages.domain.identity import DeviceIdentity
from packages.domain.ids import generate_entity_id, generate_relationship_id
from packages.domain.scope import GraphScope


def test_entity_ids_are_deterministic_uuid5_values():
    identity = DeviceIdentity(
        scope=GraphScope(
            organization_id=uuid.UUID(int=1),
            project_id=uuid.UUID(int=2),
            environment="prod",
            site_id=uuid.UUID(int=3),
        ),
        hostname="router-01",
    )
    entity_id = generate_entity_id(identity)

    assert isinstance(entity_id, uuid.UUID)
    assert entity_id.version == 5
    assert entity_id == generate_entity_id(identity)


def test_relationship_id_determinism():
    source_id = uuid.uuid4()
    target_id = uuid.uuid4()
    assert generate_relationship_id(
        RelationshipType.HAS_INTERFACE, source_id, target_id
    ) == generate_relationship_id(RelationshipType.HAS_INTERFACE, source_id, target_id)


def test_relationship_id_directionality():
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    assert generate_relationship_id(
        RelationshipType.CONNECTED_TO, first_id, second_id
    ) != generate_relationship_id(RelationshipType.CONNECTED_TO, second_id, first_id)
