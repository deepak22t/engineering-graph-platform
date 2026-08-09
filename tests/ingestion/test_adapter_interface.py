"""Tests for the Phase 3 adapter contract."""

import pytest

from packages.artifacts import ArtifactKind
from packages.ingestion.adapters import IngestionAdapter


class CiscoConfigAdapter(IngestionAdapter):
    name = "cisco_ios_config"
    version = "1"

    def supports(self, artifact_kind: ArtifactKind) -> bool:
        return artifact_kind is ArtifactKind.CISCO_IOS_RUNNING_CONFIG


def test_adapter_declares_supported_artifact_kind() -> None:
    adapter = CiscoConfigAdapter()

    assert adapter.name == "cisco_ios_config"
    assert adapter.version == "1"
    assert adapter.supports(ArtifactKind.CISCO_IOS_RUNNING_CONFIG)
    assert not adapter.supports(ArtifactKind.CDP_NEIGHBORS_DETAIL)


def test_adapter_interface_cannot_be_instantiated_without_support_rule() -> None:
    with pytest.raises(TypeError):
        IngestionAdapter()
