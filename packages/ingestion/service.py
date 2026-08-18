"""Create deterministic extraction plans from persisted artifact versions."""

from uuid import UUID

from packages.artifacts.contracts import ArtifactStatus
from packages.artifacts.persistence import ArtifactRepository
from packages.ingestion.adapter_registry import AdapterRegistry
from packages.ingestion.errors import (
    ArtifactNotFoundError,
    ArtifactVersionNotFoundError,
    ArtifactVersionNotReadyError,
    MissingArtifactStorageReferenceError,
    NoAdapterRegisteredError,
    UnsupportedArtifactKindError,
)
from packages.ingestion.models import ExtractionInput


class IngestionService:
    """Prepare extraction input without parsing source content or mutating lifecycle."""

    def __init__(self, *, repository: ArtifactRepository, registry: AdapterRegistry) -> None:
        self._repository = repository
        self._registry = registry

    async def prepare_extraction(
        self, artifact_id: UUID, version_number: int
    ) -> ExtractionInput:
        """Return one validated, immutable handoff for the selected adapter."""
        artifact = await self._repository.get_artifact(artifact_id)
        if artifact is None:
            raise ArtifactNotFoundError(artifact_id)

        version = await self._repository.get_version(artifact_id, version_number)
        if version is None or version.artifact_id != artifact.id:
            raise ArtifactVersionNotFoundError(artifact_id, version_number)
        if version.status is not ArtifactStatus.UPLOADED:
            raise ArtifactVersionNotReadyError(artifact_id, version_number, version.status)
        if not version.storage_key.strip():
            raise MissingArtifactStorageReferenceError(artifact_id, version_number)

        try:
            adapter = self._registry.select(version.artifact_kind)
        except UnsupportedArtifactKindError as error:
            raise NoAdapterRegisteredError(
                artifact_id,
                version_number,
                version.artifact_kind,
            ) from error
        return adapter.prepare_input(artifact=artifact, version=version)
