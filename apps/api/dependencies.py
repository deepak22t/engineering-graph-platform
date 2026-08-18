"""Application composition for Artifact Service dependencies."""

from contextlib import asynccontextmanager

import asyncpg
import miniopy_async
from fastapi import FastAPI, Request

from packages.artifacts import (
    ArtifactFileValidator,
    ArtifactStreamProcessor,
    ArtifactUploadService,
    MinioArtifactStorage,
    PostgresArtifactRepository,
)
from packages.common.config.settings import Settings


@asynccontextmanager
async def artifact_service_lifespan(app: FastAPI, settings: Settings):
    """Create infrastructure adapters once; routes receive only the service."""
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
    app.state.artifact_upload_service = ArtifactUploadService(
        repository=repository,
        storage=storage,
        stream_processor=ArtifactStreamProcessor(settings.artifact_max_size_bytes),
        file_validator=ArtifactFileValidator(settings.artifact_max_size_bytes),
    )
    try:
        yield
    finally:
        await pool.close()


def get_artifact_upload_service(request: Request) -> ArtifactUploadService:
    """Return the application-configured Artifact Service for an HTTP route."""
    return request.app.state.artifact_upload_service
