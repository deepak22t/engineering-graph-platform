"""Safe artifact-upload finalization after validation and streaming."""

from __future__ import annotations

from collections.abc import AsyncIterable, Awaitable, Callable
from uuid import UUID

from packages.artifacts.classification import ArtifactClassifier
from packages.artifacts.contracts import ArtifactKind, ArtifactScope
from packages.artifacts.file_validation import ArtifactFileValidator
from packages.artifacts.models import Artifact, ArtifactVersion
from packages.artifacts.persistence import ArtifactRepository
from packages.artifacts.storage import MinioArtifactStorage
from packages.artifacts.streaming import ArtifactStreamProcessor, TemporaryArtifact


class ArtifactUploadService:
    """Own artifact streaming, validation, version policy, storage, and persistence."""

    def __init__(
        self,
        *,
        repository: ArtifactRepository,
        storage: MinioArtifactStorage,
        classifier: type[ArtifactClassifier] = ArtifactClassifier,
        stream_processor: ArtifactStreamProcessor | None = None,
        file_validator: ArtifactFileValidator | None = None,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._classifier = classifier
        self._stream_processor = stream_processor
        self._file_validator = file_validator

    async def upload_initial(
        self,
        *,
        scope: ArtifactScope,
        original_filename: str,
        content_type: str,
        chunks: AsyncIterable[bytes],
    ) -> tuple[Artifact, ArtifactVersion]:
        """Stream, validate, classify, store, and persist a first upload."""
        temporary_artifact = await self._stream_to_temporary_file(chunks)
        try:
            artifact_kind = self._validate_temporary_file(
                original_filename=original_filename,
                content_type=content_type,
                temporary_artifact=temporary_artifact,
            )
        except Exception:
            temporary_artifact.cleanup()
            raise
        return await self._finalize_initial_upload(
            scope=scope,
            original_filename=original_filename,
            content_type=content_type,
            temporary_artifact=temporary_artifact,
            artifact_kind=artifact_kind,
        )

    async def upload_next(
        self,
        *,
        artifact_id: UUID,
        original_filename: str,
        content_type: str,
        chunks: AsyncIterable[bytes],
    ) -> tuple[Artifact, ArtifactVersion]:
        """Stream, validate, and apply checksum-based later-version policy."""
        temporary_artifact = await self._stream_to_temporary_file(chunks)
        try:
            artifact_kind = self._validate_temporary_file(
                original_filename=original_filename,
                content_type=content_type,
                temporary_artifact=temporary_artifact,
            )
        except Exception:
            temporary_artifact.cleanup()
            raise
        return await self._finalize_next_upload(
            artifact_id=artifact_id,
            original_filename=original_filename,
            content_type=content_type,
            temporary_artifact=temporary_artifact,
            artifact_kind=artifact_kind,
        )

    async def finalize_initial_upload(
        self,
        *,
        scope: ArtifactScope,
        original_filename: str,
        content_type: str,
        temporary_artifact: TemporaryArtifact,
    ) -> tuple[Artifact, ArtifactVersion]:
        """Finalize a pre-streamed upload; retained for application tests and reuse."""
        return await self._finalize_initial_upload(
            scope=scope,
            original_filename=original_filename,
            content_type=content_type,
            temporary_artifact=temporary_artifact,
        )

    async def finalize_next_upload(
        self,
        *,
        artifact_id: UUID,
        original_filename: str,
        content_type: str,
        temporary_artifact: TemporaryArtifact,
    ) -> tuple[Artifact, ArtifactVersion]:
        """Finalize a pre-streamed later upload; retained for application tests and reuse."""
        return await self._finalize_next_upload(
            artifact_id=artifact_id,
            original_filename=original_filename,
            content_type=content_type,
            temporary_artifact=temporary_artifact,
        )

    async def _finalize_initial_upload(
        self,
        *,
        scope: ArtifactScope,
        original_filename: str,
        content_type: str,
        temporary_artifact: TemporaryArtifact,
        artifact_kind: ArtifactKind | None = None,
    ) -> tuple[Artifact, ArtifactVersion]:
        artifact = Artifact(scope=scope)
        return await self._finalize_new_version(
            artifact=artifact,
            version_number=1,
            original_filename=original_filename,
            content_type=content_type,
            temporary_artifact=temporary_artifact,
            artifact_kind=artifact_kind,
            create_record=lambda version: self._repository.create_artifact_with_initial_version(
                artifact, version
            ),
        )

    async def _finalize_next_upload(
        self,
        *,
        artifact_id: UUID,
        original_filename: str,
        content_type: str,
        temporary_artifact: TemporaryArtifact,
        artifact_kind: ArtifactKind | None = None,
    ) -> tuple[Artifact, ArtifactVersion]:
        try:
            artifact = await self._repository.get_artifact(artifact_id)
            if artifact is None:
                raise ValueError("artifact does not exist.")

            resolved_kind = artifact_kind or self._classifier.classify_file(
                temporary_artifact.path, filename=original_filename
            )
            latest_version = await self._repository.get_latest_version(artifact_id)
            if latest_version is None:
                raise ValueError("artifact has no existing version.")
            if latest_version.sha256_checksum == temporary_artifact.sha256_checksum:
                temporary_artifact.cleanup()
                return artifact, latest_version
        except Exception:
            temporary_artifact.cleanup()
            raise

        return await self._finalize_new_version(
            artifact=artifact,
            version_number=latest_version.version_number + 1,
            original_filename=original_filename,
            content_type=content_type,
            temporary_artifact=temporary_artifact,
            artifact_kind=resolved_kind,
            create_record=self._repository.create_version,
        )

    async def _stream_to_temporary_file(self, chunks: AsyncIterable[bytes]) -> TemporaryArtifact:
        if self._stream_processor is None:
            raise RuntimeError("artifact stream processor is not configured.")
        return await self._stream_processor.process(chunks)

    def _validate_temporary_file(
        self,
        *,
        original_filename: str,
        content_type: str,
        temporary_artifact: TemporaryArtifact,
    ) -> ArtifactKind:
        if self._file_validator is None:
            raise RuntimeError("artifact file validator is not configured.")
        return self._file_validator.validate_file(
            filename=original_filename,
            content_type=content_type,
            path=temporary_artifact.path,
            size_bytes=temporary_artifact.size_bytes,
        )

    async def _finalize_new_version(
        self,
        *,
        artifact: Artifact,
        version_number: int,
        original_filename: str,
        content_type: str,
        temporary_artifact: TemporaryArtifact,
        artifact_kind: ArtifactKind | None,
        create_record: Callable[[ArtifactVersion], Awaitable[None]],
    ) -> tuple[Artifact, ArtifactVersion]:
        storage_key: str | None = None
        try:
            resolved_kind = artifact_kind or self._classifier.classify_file(
                temporary_artifact.path, filename=original_filename
            )
            storage_key = await self._storage.store_original(
                artifact_id=artifact.id,
                version_number=version_number,
                temporary_artifact=temporary_artifact,
                content_type=content_type,
            )
            version = ArtifactVersion(
                artifact_id=artifact.id,
                version_number=version_number,
                original_filename=original_filename,
                artifact_kind=resolved_kind,
                content_type=content_type,
                size_bytes=temporary_artifact.size_bytes,
                sha256_checksum=temporary_artifact.sha256_checksum,
                storage_key=storage_key,
            )
            await create_record(version)
            return artifact, version
        except Exception:
            if storage_key is not None:
                await self._storage.remove_original(
                    artifact_id=artifact.id, version_number=version_number
                )
            raise
        finally:
            temporary_artifact.cleanup()
