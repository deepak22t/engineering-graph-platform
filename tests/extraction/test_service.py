"""Tests for synchronous deterministic extraction lifecycle transitions."""

from uuid import UUID

import pytest

from packages.artifacts import ArtifactKind, ArtifactScope, ArtifactStatus
from packages.extraction.contracts import VerifiedArtifactText
from packages.extraction.errors import UnsupportedExtractionKindError
from packages.extraction.service import ExtractionService
from packages.ingestion.models import ExtractionInput


def extraction_input(
    kind: ArtifactKind = ArtifactKind.CISCO_IOS_RUNNING_CONFIG,
) -> ExtractionInput:
    return ExtractionInput(
        artifact_id=UUID("11111111-1111-1111-1111-111111111111"),
        artifact_version_id=UUID("22222222-2222-2222-2222-222222222222"),
        version_number=1,
        scope=ArtifactScope(
            organization_id=UUID("33333333-3333-3333-3333-333333333333"),
            project_id=UUID("44444444-4444-4444-4444-444444444444"),
            environment="production",
            site_id=UUID("55555555-5555-5555-5555-555555555555"),
        ),
        artifact_kind=kind,
        sha256_checksum="a" * 64,
        original_filename="router.cfg",
        storage_key="artifacts/trusted/versions/1/original",
        adapter_name="cisco_ios_config",
        adapter_version="1",
    )


class FakeRepository:
    def __init__(self) -> None:
        self.status_updates: list[ArtifactStatus] = []

    async def update_version_status(
        self, artifact_id: UUID, version_number: int, status: ArtifactStatus
    ) -> None:
        self.status_updates.append(status)


class FakeIngestionService:
    def __init__(self, value: ExtractionInput) -> None:
        self._value = value

    async def prepare_extraction(self, artifact_id: UUID, version_number: int) -> ExtractionInput:
        return self._value


class FakeContentReader:
    def __init__(self, text: str | Exception) -> None:
        self._text = text
        self.read_count = 0

    async def read_verified_text(self, source: ExtractionInput) -> VerifiedArtifactText:
        if isinstance(self._text, Exception):
            raise self._text
        return VerifiedArtifactText(
            text=self._text,
            byte_count=len(self._text.encode()),
        )


@pytest.mark.asyncio
async def test_successful_extraction_transitions_version_to_processed() -> None:
    source = extraction_input()
    repository = FakeRepository()
    service = ExtractionService(
        repository=repository,
        ingestion_service=FakeIngestionService(source),
        content_reader=FakeContentReader("hostname router-01\n"),
    )

    result = await service.extract(source.artifact_id, source.version_number)

    assert repository.status_updates == [ArtifactStatus.PROCESSING, ArtifactStatus.PROCESSED]
    assert result.artifact_id == source.artifact_id
    assert [proposal.display_name for proposal in result.entity_proposals] == ["router-01"]


@pytest.mark.asyncio
async def test_extraction_failure_marks_version_failed_and_reraises() -> None:
    source = extraction_input()
    repository = FakeRepository()
    service = ExtractionService(
        repository=repository,
        ingestion_service=FakeIngestionService(source),
        content_reader=FakeContentReader(ValueError("checksum mismatch")),
    )

    with pytest.raises(ValueError, match="checksum mismatch"):
        await service.extract(source.artifact_id, source.version_number)

    assert repository.status_updates == [ArtifactStatus.PROCESSING, ArtifactStatus.FAILED]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "artifact_kind",
    (ArtifactKind.JSON, ArtifactKind.YAML, ArtifactKind.CSV, ArtifactKind.TEXT),
)
async def test_generic_kind_is_rejected_without_reading_or_creating_graph_facts(
    artifact_kind: ArtifactKind,
) -> None:
    source = extraction_input(artifact_kind)
    repository = FakeRepository()
    content_reader = FakeContentReader('{"not": "an engineering schema"}\n')
    service = ExtractionService(
        repository=repository,
        ingestion_service=FakeIngestionService(source),
        content_reader=content_reader,
    )

    with pytest.raises(UnsupportedExtractionKindError, match=artifact_kind.value):
        await service.extract(source.artifact_id, source.version_number)

    assert content_reader.read_count == 0
    assert repository.status_updates == [ArtifactStatus.PROCESSING, ArtifactStatus.FAILED]


@pytest.mark.asyncio
async def test_cdp_extraction_transitions_version_to_processed() -> None:
    source = extraction_input(ArtifactKind.CDP_NEIGHBORS_DETAIL)
    repository = FakeRepository()
    service = ExtractionService(
        repository=repository,
        ingestion_service=FakeIngestionService(source),
        content_reader=FakeContentReader(
            "Device ID: switch-01\n"
            "Interface: GigabitEthernet0/1, Port ID (outgoing port): GigabitEthernet0/2\n"
        ),
    )

    result = await service.extract(source.artifact_id, source.version_number)

    assert repository.status_updates == [ArtifactStatus.PROCESSING, ArtifactStatus.PROCESSED]
    assert result.artifact_kind == ArtifactKind.CDP_NEIGHBORS_DETAIL.value
    assert len(result.relationship_proposals) == 1


@pytest.mark.asyncio
async def test_lldp_extraction_transitions_version_to_processed() -> None:
    source = extraction_input(ArtifactKind.LLDP_NEIGHBORS_DETAIL)
    repository = FakeRepository()
    service = ExtractionService(
        repository=repository,
        ingestion_service=FakeIngestionService(source),
        content_reader=FakeContentReader(
            "Local Intf: GigabitEthernet0/1\n"
            "Chassis id: 0011.2233.4455\n"
            "Port id: GigabitEthernet0/2\n"
        ),
    )

    result = await service.extract(source.artifact_id, source.version_number)

    assert repository.status_updates == [ArtifactStatus.PROCESSING, ArtifactStatus.PROCESSED]
    assert result.artifact_kind == ArtifactKind.LLDP_NEIGHBORS_DETAIL.value
    assert len(result.relationship_proposals) == 1
