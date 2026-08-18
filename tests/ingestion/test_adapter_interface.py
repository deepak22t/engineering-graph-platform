"""Tests for the Phase 3 adapter contract."""

from uuid import UUID

import pytest

from packages.artifacts import ArtifactKind, ArtifactScope
from packages.extraction import VerifiedArtifactText
from packages.ingestion.adapters import IngestionAdapter
from packages.ingestion.models import ExtractionInput


class CiscoConfigAdapter(IngestionAdapter):
    name = "cisco_ios_config"
    version = "1"

    def supports(self, artifact_kind: ArtifactKind) -> bool:
        return artifact_kind is ArtifactKind.CISCO_IOS_RUNNING_CONFIG


def extraction_input() -> ExtractionInput:
    return ExtractionInput(
        artifact_id=UUID(int=1),
        artifact_version_id=UUID(int=2),
        version_number=1,
        scope=ArtifactScope(
            organization_id=UUID(int=3),
            project_id=UUID(int=4),
            environment="production",
            site_id=UUID(int=5),
        ),
        artifact_kind=ArtifactKind.CISCO_IOS_RUNNING_CONFIG,
        sha256_checksum="a" * 64,
        original_filename="router.cfg",
        storage_key="artifacts/1/versions/1/original",
        adapter_name="cisco_ios_config",
        adapter_version="1",
    )


def test_adapter_declares_supported_artifact_kind() -> None:
    adapter = CiscoConfigAdapter()

    assert adapter.name == "cisco_ios_config"
    assert adapter.version == "1"
    assert adapter.supports(ArtifactKind.CISCO_IOS_RUNNING_CONFIG)
    assert not adapter.supports(ArtifactKind.CDP_NEIGHBORS_DETAIL)


def test_adapter_interface_cannot_be_instantiated_without_support_rule() -> None:
    with pytest.raises(TypeError):
        IngestionAdapter()


@pytest.mark.asyncio
async def test_adapter_execution_contract_requires_a_configured_parser() -> None:
    adapter = CiscoConfigAdapter()

    with pytest.raises(NotImplementedError, match="no deterministic extraction parser configured"):
        await adapter.extract(
            extraction_input=extraction_input(),
            source=VerifiedArtifactText(text="hostname router-01\n", byte_count=19),
        )
