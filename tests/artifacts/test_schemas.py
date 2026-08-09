"""Tests for the Phase 2 Artifact API serialization contract."""

from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from packages.artifacts import Artifact, ArtifactKind, ArtifactScope, ArtifactVersion
from packages.schemas.artifacts import (
    ArtifactResponse,
    ArtifactUploadMetadata,
    ArtifactUploadResponse,
    ArtifactVersionResponse,
)


def records() -> tuple[Artifact, ArtifactVersion]:
    scope = ArtifactScope(
        organization_id=UUID(int=1),
        project_id=UUID(int=2),
        environment="prod",
        site_id=UUID(int=3),
    )
    artifact = Artifact(
        id=UUID(int=10),
        scope=scope,
        created_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
    )
    version = ArtifactVersion(
        id=UUID(int=11),
        artifact_id=artifact.id,
        version_number=1,
        original_filename="router-01-running-config.txt",
        artifact_kind=ArtifactKind.CISCO_IOS_RUNNING_CONFIG,
        content_type="text/plain",
        size_bytes=42,
        sha256_checksum="a" * 64,
        storage_key="artifacts/10/versions/1/original",
        uploaded_at="2026-08-09T10:00:00Z",
        created_at="2026-08-09T10:00:01Z",
        updated_at="2026-08-09T10:00:02Z",
    )
    return artifact, version


def upload_metadata(**overrides) -> ArtifactUploadMetadata:
    artifact, _ = records()
    values = {
        "scope": artifact.scope,
        "original_filename": "router-01-running-config.txt",
    }
    values.update(overrides)
    return ArtifactUploadMetadata(**values)


def test_upload_metadata_requires_scope_and_non_empty_filename():
    metadata = upload_metadata()
    assert metadata.scope.site_id == UUID(int=3)
    assert metadata.original_filename == "router-01-running-config.txt"

    with pytest.raises(ValidationError):
        upload_metadata(original_filename="   ")
    with pytest.raises(ValidationError):
        ArtifactUploadMetadata(original_filename="router-01-running-config.txt")


def test_upload_metadata_rejects_invalid_scope_values_and_client_artifact_kind():
    with pytest.raises(ValidationError):
        upload_metadata(
            scope={
                "organization_id": "not-a-uuid",
                "project_id": UUID(int=2),
                "environment": "prod",
                "site_id": UUID(int=3),
            }
        )
    with pytest.raises(ValidationError):
        upload_metadata(
            scope={
                "organization_id": UUID(int=1),
                "project_id": UUID(int=2),
                "environment": "   ",
                "site_id": UUID(int=3),
            }
        )
    with pytest.raises(ValidationError):
        upload_metadata(artifact_kind="cdp_neighbors_detail")


def test_upload_response_represents_the_created_artifact_and_first_version():
    artifact, version = records()
    response = ArtifactUploadResponse.from_records(artifact, version)
    assert response.artifact.id == artifact.id
    assert response.version.artifact_id == artifact.id
    assert response.version.version_number == 1


def test_read_response_contracts_serialize_only_artifact_records():
    artifact, version = records()
    assert ArtifactResponse.from_artifact(artifact).model_dump() == artifact.model_dump()
    version_response = ArtifactVersionResponse.from_version(version)
    assert version_response.model_dump() == version.model_dump(exclude={"storage_key"})
    assert "storage_key" not in version_response.model_dump()
