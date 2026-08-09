"""Tests for deterministic ingestion adapter selection."""

import pytest

from packages.artifacts import ArtifactKind
from packages.ingestion import (
    AdapterRegistry,
    DuplicateAdapterRegistrationError,
    UnsupportedArtifactKindError,
)
from packages.ingestion.adapters import IngestionAdapter


class StaticAdapter(IngestionAdapter):
    def __init__(self, *, name: str, supported_kinds: frozenset[ArtifactKind]) -> None:
        self.name = name
        self.version = "1"
        self._supported_kinds = supported_kinds

    def supports(self, artifact_kind: ArtifactKind) -> bool:
        return artifact_kind in self._supported_kinds


def test_registry_selects_the_only_adapter_for_a_kind() -> None:
    adapter = StaticAdapter(
        name="cisco_ios_config",
        supported_kinds=frozenset({ArtifactKind.CISCO_IOS_RUNNING_CONFIG}),
    )

    assert AdapterRegistry([adapter]).select(ArtifactKind.CISCO_IOS_RUNNING_CONFIG) is adapter


def test_registry_rejects_duplicate_adapter_claims() -> None:
    first = StaticAdapter(name="first", supported_kinds=frozenset({ArtifactKind.JSON}))
    second = StaticAdapter(name="second", supported_kinds=frozenset({ArtifactKind.JSON}))

    with pytest.raises(DuplicateAdapterRegistrationError, match="json: first, second"):
        AdapterRegistry([first, second])


def test_registry_rejects_a_kind_with_no_registered_adapter() -> None:
    registry = AdapterRegistry([])

    with pytest.raises(UnsupportedArtifactKindError, match="csv"):
        registry.select(ArtifactKind.CSV)
