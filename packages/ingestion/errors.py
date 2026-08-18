"""Errors raised while routing stored artifacts to ingestion adapters."""

from uuid import UUID

from packages.artifacts.contracts import ArtifactKind, ArtifactStatus


class IngestionError(ValueError):
    """Base error for deterministic ingestion planning."""


class AdapterRegistryError(IngestionError):
    """Base error for deterministic ingestion adapter selection."""


class DuplicateAdapterRegistrationError(AdapterRegistryError):
    """Raised when multiple adapters claim the same artifact kind."""

    def __init__(self, artifact_kind: ArtifactKind, adapter_names: tuple[str, ...]) -> None:
        self.artifact_kind = artifact_kind
        self.adapter_names = adapter_names
        super().__init__(
            f"multiple adapters are registered for {artifact_kind.value}: "
            f"{', '.join(adapter_names)}."
        )


class UnsupportedArtifactKindError(AdapterRegistryError):
    """Raised when no adapter is registered for a stored artifact kind."""

    def __init__(self, artifact_kind: ArtifactKind) -> None:
        self.artifact_kind = artifact_kind
        super().__init__(f"no ingestion adapter is registered for {artifact_kind.value}.")


class NoAdapterRegisteredError(AdapterRegistryError):
    """Raised when a persisted artifact version has no registered adapter."""

    def __init__(self, artifact_id: UUID, version_number: int, artifact_kind: ArtifactKind) -> None:
        self.artifact_id = artifact_id
        self.version_number = version_number
        self.artifact_kind = artifact_kind
        AdapterRegistryError.__init__(
            self,
            f"artifact {artifact_id} version {version_number} has no adapter registered "
            f"for {artifact_kind.value}.",
        )


class ArtifactNotFoundError(IngestionError):
    """Raised when an ingestion request names no persisted artifact."""

    def __init__(self, artifact_id: UUID) -> None:
        self.artifact_id = artifact_id
        super().__init__(f"artifact {artifact_id} does not exist.")


class ArtifactVersionNotFoundError(IngestionError):
    """Raised when an ingestion request names no version of its artifact."""

    def __init__(self, artifact_id: UUID, version_number: int) -> None:
        self.artifact_id = artifact_id
        self.version_number = version_number
        super().__init__(f"artifact {artifact_id} has no version {version_number}.")


class ArtifactVersionNotReadyError(IngestionError):
    """Raised when a version is not ready for an extraction plan."""

    def __init__(self, artifact_id: UUID, version_number: int, status: ArtifactStatus) -> None:
        self.artifact_id = artifact_id
        self.version_number = version_number
        self.status = status
        super().__init__(
            f"artifact {artifact_id} version {version_number} is {status.value}, not uploaded."
        )


class MissingArtifactStorageReferenceError(IngestionError):
    """Raised when persisted metadata has no trusted source-object reference."""

    def __init__(self, artifact_id: UUID, version_number: int) -> None:
        self.artifact_id = artifact_id
        self.version_number = version_number
        super().__init__(
            f"artifact {artifact_id} version {version_number} has no storage reference."
        )
