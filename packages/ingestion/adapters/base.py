"""Framework-independent contract for Phase 3 ingestion adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod

from packages.artifacts.contracts import ArtifactKind
from packages.artifacts.models import Artifact, ArtifactVersion
from packages.ingestion.models import ExtractionInput


class IngestionAdapter(ABC):
    """Declare and prepare one safely classified artifact kind for extraction."""

    name: str
    version: str

    @abstractmethod
    def supports(self, artifact_kind: ArtifactKind) -> bool:
        """Return whether this adapter accepts the stored artifact kind."""

    def prepare_input(self, *, artifact: Artifact, version: ArtifactVersion) -> ExtractionInput:
        """Create a typed extraction handoff without reading or parsing source bytes."""
        if version.artifact_id != artifact.id:
            raise ValueError("artifact version does not belong to the supplied artifact.")
        if not self.supports(version.artifact_kind):
            raise ValueError(
                f"adapter {self.name} does not support {version.artifact_kind.value}."
            )
        return ExtractionInput(
            artifact_id=artifact.id,
            artifact_version_id=version.id,
            version_number=version.version_number,
            scope=artifact.scope,
            artifact_kind=version.artifact_kind,
            sha256_checksum=version.sha256_checksum,
            original_filename=version.original_filename,
            storage_key=version.storage_key,
            adapter_name=self.name,
            adapter_version=self.version,
        )
