"""Tests for deterministic ingestion-plan creation."""

from uuid import UUID

import pytest

from packages.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactScope,
    ArtifactStatus,
    ArtifactVersion,
)
from packages.ingestion import (
    AdapterRegistry,
    ArtifactNotFoundError,
    ArtifactVersionNotFoundError,
    ArtifactVersionNotReadyError,
    IngestionService,
    MissingArtifactStorageReferenceError,
    NoAdapterRegisteredError,
    build_default_adapter_registry,
)
from packages.ingestion.adapters import IngestionAdapter


class StaticAdapter(IngestionAdapter):
    def __init__(self, *, name: str, artifact_kind: ArtifactKind) -> None:
        self.name = name
        self.version = "1"
        self._artifact_kind = artifact_kind

    def supports(self, artifact_kind: ArtifactKind) -> bool:
        return artifact_kind is self._artifact_kind


class FakeRepository:
    def __init__(self, artifact: Artifact | None, version: ArtifactVersion | None) -> None:
        self.artifact = artifact
        self.version = version
        self.version_requests: list[tuple[UUID, int]] = []

    async def get_artifact(self, artifact_id: UUID) -> Artifact | None:
        if self.artifact is not None and self.artifact.id == artifact_id:
            return self.artifact
        return None

    async def get_version(self, artifact_id: UUID, version_number: int) -> ArtifactVersion | None:
        self.version_requests.append((artifact_id, version_number))
        if (
            self.version is not None
            and self.version.artifact_id == artifact_id
            and self.version.version_number == version_number
        ):
            return self.version
        return None


def artifact() -> Artifact:
    return Artifact(
        id=UUID(int=1),
        scope=ArtifactScope(
            organization_id=UUID(int=2),
            project_id=UUID(int=3),
            environment="prod",
            site_id=UUID(int=4),
        ),
    )


def version(
    *,
    artifact_kind: ArtifactKind,
    status: ArtifactStatus = ArtifactStatus.UPLOADED,
) -> ArtifactVersion:
    return ArtifactVersion(
        id=UUID(int=5),
        artifact_id=UUID(int=1),
        version_number=1,
        original_filename="source.txt",
        artifact_kind=artifact_kind,
        content_type="text/plain",
        size_bytes=10,
        sha256_checksum="a" * 64,
        storage_key="artifacts/00000000-0000-0000-0000-000000000001/versions/1/original",
        status=status,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "artifact_kind, adapter_name",
    [
        (ArtifactKind.CISCO_IOS_RUNNING_CONFIG, "cisco_ios_config"),
        (ArtifactKind.CDP_NEIGHBORS_DETAIL, "cdp_neighbor_detail"),
        (ArtifactKind.LLDP_NEIGHBORS_DETAIL, "lldp_neighbor_detail"),
        (ArtifactKind.JSON, "json"),
        (ArtifactKind.YAML, "yaml"),
        (ArtifactKind.CSV, "csv"),
        (ArtifactKind.TEXT, "text"),
    ],
)
async def test_prepare_extraction_returns_exact_immutable_handoff(
    artifact_kind: ArtifactKind, adapter_name: str
) -> None:
    source_artifact = artifact()
    source_version = version(artifact_kind=artifact_kind)
    service = IngestionService(
        repository=FakeRepository(source_artifact, source_version),
        registry=build_default_adapter_registry(),
    )

    extraction_input = await service.prepare_extraction(source_artifact.id, 1)

    assert extraction_input.artifact_id == source_artifact.id
    assert extraction_input.artifact_version_id == source_version.id
    assert extraction_input.version_number == 1
    assert extraction_input.scope == source_artifact.scope
    assert extraction_input.artifact_kind is artifact_kind
    assert extraction_input.sha256_checksum == source_version.sha256_checksum
    assert extraction_input.original_filename == source_version.original_filename
    assert extraction_input.storage_key == source_version.storage_key
    assert extraction_input.adapter_name == adapter_name
    assert extraction_input.adapter_version == "1"
    assert source_version.status is ArtifactStatus.UPLOADED


@pytest.mark.asyncio
async def test_prepare_extraction_rejects_missing_artifact() -> None:
    service = IngestionService(repository=FakeRepository(None, None), registry=AdapterRegistry([]))

    with pytest.raises(ArtifactNotFoundError, match="does not exist"):
        await service.prepare_extraction(UUID(int=1), 1)


@pytest.mark.asyncio
async def test_prepare_extraction_rejects_missing_version() -> None:
    source_artifact = artifact()
    service = IngestionService(
        repository=FakeRepository(source_artifact, None), registry=AdapterRegistry([])
    )

    with pytest.raises(ArtifactVersionNotFoundError, match="has no version"):
        await service.prepare_extraction(source_artifact.id, 1)


@pytest.mark.asyncio
async def test_prepare_extraction_does_not_process_a_version_early() -> None:
    source_artifact = artifact()
    source_version = version(
        artifact_kind=ArtifactKind.CISCO_IOS_RUNNING_CONFIG,
        status=ArtifactStatus.PROCESSING,
    )
    service = IngestionService(
        repository=FakeRepository(source_artifact, source_version),
        registry=AdapterRegistry(
            [
                StaticAdapter(
                    name="cisco_ios_config",
                    artifact_kind=ArtifactKind.CISCO_IOS_RUNNING_CONFIG,
                )
            ]
        ),
    )

    with pytest.raises(ArtifactVersionNotReadyError, match="processing, not uploaded"):
        await service.prepare_extraction(source_artifact.id, 1)

    assert source_version.status is ArtifactStatus.PROCESSING


@pytest.mark.asyncio
async def test_prepare_extraction_rejects_missing_storage_reference() -> None:
    source_artifact = artifact()
    source_version = version(artifact_kind=ArtifactKind.TEXT).model_copy(
        update={"storage_key": " "}
    )
    service = IngestionService(
        repository=FakeRepository(source_artifact, source_version),
        registry=AdapterRegistry([StaticAdapter(name="text", artifact_kind=ArtifactKind.TEXT)]),
    )

    with pytest.raises(MissingArtifactStorageReferenceError, match="no storage reference"):
        await service.prepare_extraction(source_artifact.id, 1)


@pytest.mark.asyncio
async def test_prepare_extraction_rejects_a_kind_without_an_adapter() -> None:
    source_artifact = artifact()
    service = IngestionService(
        repository=FakeRepository(source_artifact, version(artifact_kind=ArtifactKind.CSV)),
        registry=AdapterRegistry([]),
    )

    with pytest.raises(
        NoAdapterRegisteredError, match="version 1 has no adapter registered for csv"
    ) as raised:
        await service.prepare_extraction(source_artifact.id, 1)

    error = raised.value
    assert error.artifact_id == source_artifact.id
    assert error.version_number == 1
    assert error.artifact_kind is ArtifactKind.CSV
