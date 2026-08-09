"""Tests for safe Artifact metadata finalization and version behavior."""

import hashlib
from pathlib import Path
from uuid import UUID

import pytest

from packages.artifacts import (
    ArtifactFileValidator,
    ArtifactScope,
    ArtifactStreamProcessor,
    ArtifactUploadService,
    TemporaryArtifact,
)


class FakeStorage:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.stored: list[tuple[UUID, int, bytes]] = []
        self.removed: list[tuple[UUID, int]] = []

    async def store_original(
        self, *, artifact_id, version_number, temporary_artifact, content_type
    ):
        if self.failure is not None:
            raise self.failure
        self.stored.append((artifact_id, version_number, temporary_artifact.path.read_bytes()))
        return f"artifacts/{artifact_id}/versions/{version_number}/original"

    async def remove_original(self, *, artifact_id, version_number):
        self.removed.append((artifact_id, version_number))


class FakeRepository:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.records: list[tuple] = []
        self.artifacts: dict[UUID, object] = {}
        self.versions: dict[UUID, list] = {}

    async def create_artifact_with_initial_version(self, artifact, version) -> None:
        self._raise_if_needed()
        self.records.append((artifact, version))
        self.artifacts[artifact.id] = artifact
        self.versions[artifact.id] = [version]

    async def get_artifact(self, artifact_id):
        return self.artifacts.get(artifact_id)

    async def get_latest_version(self, artifact_id):
        versions = self.versions.get(artifact_id, [])
        return versions[-1] if versions else None

    async def create_version(self, version) -> None:
        self._raise_if_needed()
        self.versions[version.artifact_id].append(version)

    def _raise_if_needed(self) -> None:
        if self.failure is not None:
            raise self.failure


def make_scope() -> ArtifactScope:
    return ArtifactScope(
        organization_id=UUID(int=1),
        project_id=UUID(int=2),
        environment="prod",
        site_id=UUID(int=3),
    )


def temporary_artifact(tmp_path: Path, content: str) -> TemporaryArtifact:
    path = tmp_path / "upload.tmp"
    raw_content = content.encode()
    path.write_bytes(raw_content)
    return TemporaryArtifact(
        path=path,
        sha256_checksum=hashlib.sha256(raw_content).hexdigest(),
        size_bytes=len(raw_content),
    )


@pytest.mark.asyncio
async def test_finalization_stores_then_persists_uploaded_metadata(tmp_path: Path):
    storage = FakeStorage()
    repository = FakeRepository()
    temporary = temporary_artifact(tmp_path, "version 17\nhostname router-01\ninterface Gi0/1\n")

    artifact, version = await ArtifactUploadService(
        repository=repository, storage=storage
    ).finalize_initial_upload(
        scope=make_scope(),
        original_filename="router.cfg",
        content_type="text/plain",
        temporary_artifact=temporary,
    )

    assert repository.records == [(artifact, version)]
    assert version.status.value == "uploaded"
    assert version.storage_key == f"artifacts/{artifact.id}/versions/1/original"
    assert not temporary.path.exists()


@pytest.mark.asyncio
async def test_same_latest_checksum_returns_existing_version_without_storage(tmp_path: Path):
    storage = FakeStorage()
    repository = FakeRepository()
    service = ArtifactUploadService(repository=repository, storage=storage)
    original = "version 17\nhostname router-01\ninterface Gi0/1\n"
    artifact, version_one = await service.finalize_initial_upload(
        scope=make_scope(),
        original_filename="router-01.cfg",
        content_type="text/plain",
        temporary_artifact=temporary_artifact(tmp_path, original),
    )

    returned_artifact, returned_version = await service.finalize_next_upload(
        artifact_id=artifact.id,
        original_filename="renamed-router.txt",
        content_type="text/plain",
        temporary_artifact=temporary_artifact(tmp_path, original),
    )

    assert returned_artifact == artifact
    assert returned_version == version_one
    assert len(storage.stored) == 1
    assert len(repository.versions[artifact.id]) == 1


@pytest.mark.asyncio
async def test_changed_checksum_creates_next_version_even_with_same_filename(tmp_path: Path):
    storage = FakeStorage()
    repository = FakeRepository()
    service = ArtifactUploadService(repository=repository, storage=storage)
    artifact, _ = await service.finalize_initial_upload(
        scope=make_scope(),
        original_filename="router-01.cfg",
        content_type="text/plain",
        temporary_artifact=temporary_artifact(
            tmp_path, "version 17\nhostname router-01\ninterface Gi0/1\n"
        ),
    )

    _, version_two = await service.finalize_next_upload(
        artifact_id=artifact.id,
        original_filename="router-01.cfg",
        content_type="text/plain",
        temporary_artifact=temporary_artifact(
            tmp_path, "version 17\nhostname router-01\ninterface Gi0/1\ndescription changed\n"
        ),
    )

    assert version_two.version_number == 2
    assert len(storage.stored) == 2
    assert [version.version_number for version in repository.versions[artifact.id]] == [1, 2]


@pytest.mark.asyncio
async def test_classification_failure_creates_no_object_or_metadata(tmp_path: Path):
    storage = FakeStorage()
    repository = FakeRepository()
    temporary = temporary_artifact(tmp_path, "unrecognized artifact")

    with pytest.raises(ValueError, match="not a supported"):
        await ArtifactUploadService(repository=repository, storage=storage).finalize_initial_upload(
            scope=make_scope(),
            original_filename="router.cfg",
            content_type="text/plain",
            temporary_artifact=temporary,
        )

    assert storage.stored == []
    assert repository.records == []
    assert not temporary.path.exists()


@pytest.mark.asyncio
async def test_storage_failure_creates_no_metadata(tmp_path: Path):
    repository = FakeRepository()
    temporary = temporary_artifact(tmp_path, "version 17\nhostname router-01\ninterface Gi0/1\n")

    with pytest.raises(RuntimeError, match="storage failed"):
        await ArtifactUploadService(
            repository=repository, storage=FakeStorage(RuntimeError("storage failed"))
        ).finalize_initial_upload(
            scope=make_scope(),
            original_filename="router.cfg",
            content_type="text/plain",
            temporary_artifact=temporary,
        )

    assert repository.records == []
    assert not temporary.path.exists()


@pytest.mark.asyncio
async def test_database_failure_removes_new_object(tmp_path: Path):
    storage = FakeStorage()
    temporary = temporary_artifact(tmp_path, "version 17\nhostname router-01\ninterface Gi0/1\n")

    with pytest.raises(RuntimeError, match="database failed"):
        await ArtifactUploadService(
            repository=FakeRepository(RuntimeError("database failed")), storage=storage
        ).finalize_initial_upload(
            scope=make_scope(),
            original_filename="router.cfg",
            content_type="text/plain",
            temporary_artifact=temporary,
        )

    assert len(storage.stored) == 1
    assert storage.removed == [(storage.stored[0][0], 1)]
    assert not temporary.path.exists()


@pytest.mark.asyncio
async def test_changed_version_database_failure_removes_only_new_object(tmp_path: Path):
    storage = FakeStorage()
    repository = FakeRepository()
    service = ArtifactUploadService(repository=repository, storage=storage)
    artifact, _ = await service.finalize_initial_upload(
        scope=make_scope(),
        original_filename="router-01.cfg",
        content_type="text/plain",
        temporary_artifact=temporary_artifact(
            tmp_path, "version 17\nhostname router-01\ninterface Gi0/1\n"
        ),
    )
    repository.failure = RuntimeError("database failed")

    with pytest.raises(RuntimeError, match="database failed"):
        await service.finalize_next_upload(
            artifact_id=artifact.id,
            original_filename="router-01.cfg",
            content_type="text/plain",
            temporary_artifact=temporary_artifact(
                tmp_path, "version 17\nhostname router-01\ninterface Gi0/1\ndescription changed\n"
            ),
        )

    assert [version.version_number for version in repository.versions[artifact.id]] == [1]
    assert storage.removed == [(artifact.id, 2)]


async def upload_chunks(content: bytes):
    midpoint = len(content) // 2
    yield content[:midpoint]
    yield content[midpoint:]


@pytest.mark.asyncio
async def test_upload_initial_keeps_streaming_and_validation_inside_service(tmp_path: Path):
    storage = FakeStorage()
    repository = FakeRepository()
    service = ArtifactUploadService(
        repository=repository,
        storage=storage,
        stream_processor=ArtifactStreamProcessor(1024, temporary_directory=tmp_path),
        file_validator=ArtifactFileValidator(1024),
    )
    content = b"version 17\nhostname router-01\ninterface Gi0/1\n"

    artifact, version = await service.upload_initial(
        scope=make_scope(),
        original_filename="router.cfg",
        content_type="text/plain",
        chunks=upload_chunks(content),
    )

    assert version.version_number == 1
    assert repository.records == [(artifact, version)]
    assert storage.stored == [(artifact.id, 1, content)]
    assert list(tmp_path.glob("egp-artifact-*.tmp")) == []
