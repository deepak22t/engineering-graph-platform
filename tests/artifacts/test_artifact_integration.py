"""Opt-in PostgreSQL and MinIO integration tests for Artifact Service."""

import hashlib
import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import miniopy_async
import pytest
from miniopy_async.error import S3Error

from packages.artifacts import (
    ArtifactFileValidator,
    ArtifactScope,
    ArtifactStreamProcessor,
    ArtifactUploadService,
    MinioArtifactStorage,
    PostgresArtifactRepository,
)
from packages.common.config.settings import get_settings
from packages.ingestion import IngestionService, build_default_adapter_registry

pytestmark = pytest.mark.integration

if os.getenv("RUN_ARTIFACT_INTEGRATION_TESTS") != "1":
    pytest.skip(
        "Set RUN_ARTIFACT_INTEGRATION_TESTS=1 with PostgreSQL and MinIO running.",
        allow_module_level=True,
    )


async def chunks(content: bytes) -> AsyncIterator[bytes]:
    midpoint = len(content) // 2
    yield content[:midpoint]
    yield content[midpoint:]


class CapturingStorage:
    def __init__(self, storage: MinioArtifactStorage) -> None:
        self._storage = storage
        self.artifact_id: UUID | None = None
        self.version_number: int | None = None

    async def store_original(self, **kwargs):
        self.artifact_id = kwargs["artifact_id"]
        self.version_number = kwargs["version_number"]
        return await self._storage.store_original(**kwargs)

    async def remove_original(self, **kwargs):
        await self._storage.remove_original(**kwargs)


class FailingInitialRepository:
    async def create_artifact_with_initial_version(self, artifact, version) -> None:
        raise RuntimeError("database write failed")


class FailingStorage:
    async def store_original(self, **kwargs):
        raise RuntimeError("storage write failed")

    async def remove_original(self, **kwargs):
        raise AssertionError("rollback is not needed when storage fails")


@pytest.fixture
async def infrastructure():
    settings = get_settings()
    pool = await asyncpg.create_pool(settings.postgres_uri)
    repository = PostgresArtifactRepository(pool)
    await repository.initialize_schema()
    storage = MinioArtifactStorage(
        miniopy_async.Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=False,
        ),
        settings.artifact_bucket_name,
    )
    try:
        yield pool, repository, storage
    finally:
        await pool.close()


def service(repository, storage) -> ArtifactUploadService:
    return ArtifactUploadService(
        repository=repository,
        storage=storage,
        stream_processor=ArtifactStreamProcessor(1_024 * 1_024),
        file_validator=ArtifactFileValidator(1_024 * 1_024),
    )


def scope() -> ArtifactScope:
    return ArtifactScope(
        organization_id=uuid4(),
        project_id=uuid4(),
        environment="integration-test",
        site_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_sanitized_cisco_config_satisfies_phase_2_and_3_exit_gates(infrastructure):
    pool, repository, storage = infrastructure
    content = (
        Path(__file__).parents[1] / "fixtures" / "artifacts" / "edge-router-01-running-config.cfg"
    ).read_bytes()
    artifact = None
    try:
        artifact, version = await service(repository, storage).upload_initial(
            scope=scope(),
            original_filename="router.cfg",
            content_type="text/plain",
            chunks=chunks(content),
        )
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT sha256_checksum, storage_key, status FROM artifact_versions WHERE id = $1",
                version.id,
            )
        assert row["sha256_checksum"] == hashlib.sha256(content).hexdigest()
        assert row["storage_key"] == version.storage_key
        assert row["status"] == "uploaded"

        extraction_input = await IngestionService(
            repository=repository,
            registry=build_default_adapter_registry(),
        ).prepare_extraction(artifact.id, version.version_number)
        assert extraction_input.artifact_id == artifact.id
        assert extraction_input.artifact_version_id == version.id
        assert extraction_input.artifact_kind.value == "cisco_ios_running_config"
        assert extraction_input.storage_key == version.storage_key
        assert extraction_input.adapter_name == "cisco_ios_config"
        assert extraction_input.adapter_version == "1"
        assert version.status.value == "uploaded"

        duplicate_artifact, duplicate_version = await service(repository, storage).upload_next(
            artifact_id=artifact.id,
            original_filename="renamed-edge-router.txt",
            content_type="text/plain",
            chunks=chunks(content),
        )
        assert duplicate_artifact == artifact
        assert duplicate_version == version
        async with pool.acquire() as connection:
            version_count = await connection.fetchval(
                "SELECT COUNT(*) FROM artifact_versions WHERE artifact_id = $1", artifact.id
            )
        assert version_count == 1

        response = await storage.open_original(storage_key=version.storage_key)
        try:
            assert await response.read() == content
        finally:
            response.release()
    finally:
        if artifact is not None:
            await storage.remove_original(artifact_id=artifact.id, version_number=1)
            async with pool.acquire() as connection:
                await connection.execute(
                    "DELETE FROM artifact_versions WHERE artifact_id = $1", artifact.id
                )
                await connection.execute("DELETE FROM artifacts WHERE id = $1", artifact.id)


@pytest.mark.asyncio
async def test_database_failure_removes_new_minio_object(infrastructure):
    _, _, storage = infrastructure
    capturing_storage = CapturingStorage(storage)
    content = (
        Path(__file__).parents[1] / "fixtures" / "artifacts" / "edge-router-01-running-config.cfg"
    ).read_bytes()

    with pytest.raises(RuntimeError, match="database write failed"):
        await service(FailingInitialRepository(), capturing_storage).upload_initial(
            scope=scope(),
            original_filename="router.cfg",
            content_type="text/plain",
            chunks=chunks(content),
        )

    assert capturing_storage.artifact_id is not None
    with pytest.raises(S3Error):
        await storage.open_original(
            storage_key=f"artifacts/{capturing_storage.artifact_id}/versions/{capturing_storage.version_number}/original"
        )


@pytest.mark.asyncio
async def test_storage_failure_creates_no_uploaded_metadata(infrastructure):
    pool, repository, _ = infrastructure
    async with pool.acquire() as connection:
        before_count = await connection.fetchval("SELECT COUNT(*) FROM artifacts")

    with pytest.raises(RuntimeError, match="storage write failed"):
        await service(repository, FailingStorage()).upload_initial(
            scope=scope(),
            original_filename="router.cfg",
            content_type="text/plain",
            chunks=chunks(b"version 17\nhostname router-01\ninterface Gi0/1\n"),
        )

    async with pool.acquire() as connection:
        after_count = await connection.fetchval("SELECT COUNT(*) FROM artifacts")
    assert after_count == before_count
