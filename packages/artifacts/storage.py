"""MinIO storage adapter for immutable ArtifactVersion source bytes."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from miniopy_async.error import S3Error

from packages.artifacts.streaming import TemporaryArtifact


class ArtifactVersionAlreadyStoredError(ValueError):
    """Raised when a caller attempts to overwrite an immutable artifact version."""


def artifact_storage_key(artifact_id: UUID, version_number: int) -> str:
    """Return the stable object key for one immutable artifact version."""
    if version_number < 1:
        raise ValueError("version_number must be at least 1.")
    return f"artifacts/{artifact_id}/versions/{version_number}/original"


class MinioArtifactStorage:
    """Store and retrieve original artifact bytes without public HTTP exposure."""

    def __init__(self, client, bucket_name: str) -> None:
        if not bucket_name or not bucket_name.strip():
            raise ValueError("bucket_name must not be blank.")
        self._client = client
        self._bucket_name = bucket_name

    async def ensure_bucket(self) -> None:
        """Create the configured bucket when it does not yet exist."""
        if not await self._client.bucket_exists(self._bucket_name):
            await self._client.make_bucket(self._bucket_name)

    async def store_original(
        self,
        *,
        artifact_id: UUID,
        version_number: int,
        temporary_artifact: TemporaryArtifact,
        content_type: str,
    ) -> str:
        """Store one original artifact version exactly once and return its object key."""
        if not content_type or not content_type.strip():
            raise ValueError("content_type must not be blank.")
        self._validate_temporary_artifact(temporary_artifact)
        storage_key = artifact_storage_key(artifact_id, version_number)

        await self.ensure_bucket()
        if await self._object_exists(storage_key):
            raise ArtifactVersionAlreadyStoredError(
                f"Artifact version already exists at {storage_key}."
            )

        with temporary_artifact.path.open("rb") as source:
            await self._client.put_object(
                self._bucket_name,
                storage_key,
                source,
                temporary_artifact.size_bytes,
                content_type=content_type,
            )
        return storage_key

    async def open_original(self, *, artifact_id: UUID, version_number: int):
        """Return the internal MinIO response stream for an original artifact version."""
        return await self._client.get_object(
            self._bucket_name,
            artifact_storage_key(artifact_id, version_number),
        )

    async def remove_original(self, *, artifact_id: UUID, version_number: int) -> None:
        """Remove a newly stored object when its metadata transaction fails."""
        await self._client.remove_object(
            self._bucket_name,
            artifact_storage_key(artifact_id, version_number),
        )

    async def _object_exists(self, storage_key: str) -> bool:
        try:
            await self._client.stat_object(self._bucket_name, storage_key)
        except S3Error as error:
            if error.code in {"NoSuchKey", "NoSuchObject"}:
                return False
            raise
        return True

    @staticmethod
    def _validate_temporary_artifact(temporary_artifact: TemporaryArtifact) -> None:
        if not isinstance(temporary_artifact.path, Path) or not temporary_artifact.path.is_file():
            raise ValueError("temporary artifact file does not exist.")
        if temporary_artifact.path.stat().st_size != temporary_artifact.size_bytes:
            raise ValueError("temporary artifact size does not match its metadata.")
