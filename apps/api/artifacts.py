"""HTTP adapters for the Artifact upload operations."""

from collections.abc import AsyncIterable
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from apps.api.dependencies import get_artifact_upload_service
from packages.artifacts import ArtifactScope, ArtifactUploadService
from packages.artifacts.streaming import DEFAULT_UPLOAD_CHUNK_SIZE_BYTES
from packages.schemas.artifacts import ArtifactUploadMetadata, ArtifactUploadResponse

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.post("", response_model=ArtifactUploadResponse, status_code=status.HTTP_201_CREATED)
async def create_artifact(
    organization_id: UUID = Form(),
    project_id: UUID = Form(),
    environment: str = Form(),
    site_id: UUID = Form(),
    file: UploadFile = File(),
    service: ArtifactUploadService = Depends(get_artifact_upload_service),
) -> ArtifactUploadResponse:
    """Create one scoped logical Artifact and its first immutable version."""
    try:
        metadata = ArtifactUploadMetadata(
            scope=ArtifactScope(
                organization_id=organization_id,
                project_id=project_id,
                environment=environment,
                site_id=site_id,
            ),
            original_filename=file.filename or "",
        )
        artifact, version = await service.upload_initial(
            scope=metadata.scope,
            original_filename=metadata.original_filename,
            content_type=file.content_type or "",
            chunks=_upload_chunks(file),
        )
        return ArtifactUploadResponse.from_records(artifact, version)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    finally:
        await file.close()


@router.post(
    "/{artifact_id}/versions",
    response_model=ArtifactUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_artifact_version(
    artifact_id: UUID,
    file: UploadFile = File(),
    service: ArtifactUploadService = Depends(get_artifact_upload_service),
) -> ArtifactUploadResponse:
    """Create a changed version or return the latest matching version."""
    try:
        artifact, version = await service.upload_next(
            artifact_id=artifact_id,
            original_filename=file.filename or "",
            content_type=file.content_type or "",
            chunks=_upload_chunks(file),
        )
        return ArtifactUploadResponse.from_records(artifact, version)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    finally:
        await file.close()


async def _upload_chunks(file: UploadFile) -> AsyncIterable[bytes]:
    """Adapt FastAPI's request stream to the Artifact Service chunk contract."""
    while chunk := await file.read(DEFAULT_UPLOAD_CHUNK_SIZE_BYTES):
        yield chunk
