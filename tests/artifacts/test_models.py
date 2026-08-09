"""Tests for Phase 2 Artifact and ArtifactVersion application records."""

from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from packages.artifacts import Artifact, ArtifactKind, ArtifactScope, ArtifactVersion


def artifact_scope() -> ArtifactScope:
    return ArtifactScope(
        organization_id=UUID(int=1),
        project_id=UUID(int=2),
        environment="prod",
        site_id=UUID(int=3),
    )


def artifact_version(**overrides) -> ArtifactVersion:
    values = {
        "id": UUID(int=10),
        "artifact_id": UUID(int=11),
        "version_number": 1,
        "original_filename": "router-01-running-config.txt",
        "artifact_kind": ArtifactKind.CISCO_IOS_RUNNING_CONFIG,
        "content_type": "text/plain",
        "size_bytes": 42,
        "sha256_checksum": "a" * 64,
        "storage_key": "artifacts/11/versions/1/original",
        "uploaded_at": "2026-08-09T10:00:00Z",
        "created_at": "2026-08-09T10:00:01Z",
        "updated_at": "2026-08-09T10:00:02Z",
    }
    values.update(overrides)
    return ArtifactVersion(**values)


def test_artifact_is_a_scoped_application_record_not_a_graph_entity():
    artifact = Artifact(
        id=UUID(int=1),
        scope=artifact_scope(),
        created_at="2026-08-09T10:00:00Z",
    )
    assert artifact.scope.site_id == UUID(int=3)
    assert artifact.created_at == datetime(2026, 8, 9, 10, tzinfo=timezone.utc)
    assert "entity_type" not in Artifact.model_fields


def test_artifact_version_contains_only_the_phase_2_storage_metadata():
    version = artifact_version()
    assert version.status.value == "uploaded"
    assert set(version.model_dump()) == {
        "id",
        "artifact_id",
        "version_number",
        "original_filename",
        "artifact_kind",
        "content_type",
        "size_bytes",
        "sha256_checksum",
        "storage_key",
        "status",
        "uploaded_at",
        "created_at",
        "updated_at",
    }


def test_artifact_version_rejects_invalid_or_future_phase_fields():
    with pytest.raises(ValidationError):
        artifact_version(size_bytes=0)
    with pytest.raises(ValidationError):
        artifact_version(sha256_checksum="not-a-sha256")
    with pytest.raises(ValidationError):
        artifact_version(original_filename="   ")
    with pytest.raises(ValidationError):
        artifact_version(parser_result={"devices": []})


def test_artifact_version_is_immutable():
    version = artifact_version()
    with pytest.raises(ValidationError):
        version.status = "processed"
