"""Deterministic selection of one ingestion adapter per artifact kind."""

from collections.abc import Iterable

from packages.artifacts.contracts import ArtifactKind
from packages.ingestion.adapters import IngestionAdapter
from packages.ingestion.errors import (
    DuplicateAdapterRegistrationError,
    UnsupportedArtifactKindError,
)


class AdapterRegistry:
    """Resolve a safely classified artifact kind to one declared adapter."""

    def __init__(self, adapters: Iterable[IngestionAdapter]) -> None:
        self._adapters_by_kind = self._build_mapping(tuple(adapters))

    def select(self, artifact_kind: ArtifactKind) -> IngestionAdapter:
        """Return the only adapter registered for the stored artifact kind."""
        try:
            return self._adapters_by_kind[artifact_kind]
        except KeyError as error:
            raise UnsupportedArtifactKindError(artifact_kind) from error

    @staticmethod
    def _build_mapping(
        adapters: tuple[IngestionAdapter, ...],
    ) -> dict[ArtifactKind, IngestionAdapter]:
        adapters_by_kind: dict[ArtifactKind, IngestionAdapter] = {}
        for artifact_kind in ArtifactKind:
            matching_adapters = tuple(
                adapter for adapter in adapters if adapter.supports(artifact_kind)
            )
            if len(matching_adapters) > 1:
                raise DuplicateAdapterRegistrationError(
                    artifact_kind,
                    tuple(adapter.name for adapter in matching_adapters),
                )
            if matching_adapters:
                adapters_by_kind[artifact_kind] = matching_adapters[0]
        return adapters_by_kind
