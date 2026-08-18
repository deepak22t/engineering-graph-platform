"""Phase 4 tests for deterministic output and parser package boundaries."""

import ast
import hashlib
from collections import deque
from pathlib import Path
from uuid import UUID

import pytest

from packages.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactScope,
    ArtifactStatus,
    ArtifactVersion,
)
from packages.domain.enums import EntityType
from packages.extraction import ArtifactContentReader
from packages.extraction.service import ExtractionService
from packages.ingestion import IngestionService, build_default_adapter_registry

_REPOSITORY_ROOT = Path(__file__).parents[2]
_PARSER_MODULES = (
    _REPOSITORY_ROOT / "packages" / "extraction" / "cisco_ios" / "parser.py",
    _REPOSITORY_ROOT / "packages" / "extraction" / "cdp" / "parser.py",
    _REPOSITORY_ROOT / "packages" / "extraction" / "lldp" / "parser.py",
)
_FORBIDDEN_IMPORT_ROOTS = {"neo4j", "fastapi", "asyncpg", "sqlalchemy", "psycopg"}


class MemoryStream:
    def __init__(self, content: bytes) -> None:
        self._chunks = deque((content[:11], content[11:]))
        self.closed = False

    async def read(self, size: int = -1) -> bytes:
        return self._chunks.popleft() if self._chunks else b""

    async def close(self) -> None:
        self.closed = True


class MemoryStorage:
    def __init__(self, content: bytes) -> None:
        self._content = content
        self.storage_keys: list[str] = []

    async def open_original(self, *, storage_key: str) -> MemoryStream:
        self.storage_keys.append(storage_key)
        return MemoryStream(self._content)


class MemoryRepository:
    def __init__(self, artifact: Artifact, version: ArtifactVersion) -> None:
        self.artifact = artifact
        self.version = version
        self.status_updates: list[ArtifactStatus] = []

    async def get_artifact(self, artifact_id: UUID) -> Artifact | None:
        return self.artifact if artifact_id == self.artifact.id else None

    async def get_version(self, artifact_id: UUID, version_number: int) -> ArtifactVersion | None:
        if (
            artifact_id == self.version.artifact_id
            and version_number == self.version.version_number
        ):
            return self.version
        return None

    async def update_version_status(
        self, artifact_id: UUID, version_number: int, status: ArtifactStatus
    ) -> None:
        assert artifact_id == self.version.artifact_id
        assert version_number == self.version.version_number
        self.status_updates.append(status)
        self.version = self.version.model_copy(update={"status": status})


def records(content: bytes) -> tuple[Artifact, ArtifactVersion]:
    artifact = Artifact(
        id=UUID(int=1),
        scope=ArtifactScope(
            organization_id=UUID(int=2),
            project_id=UUID(int=3),
            environment="production",
            site_id=UUID(int=4),
        ),
    )
    return artifact, ArtifactVersion(
        id=UUID(int=5),
        artifact_id=artifact.id,
        version_number=1,
        original_filename="router.cfg",
        artifact_kind=ArtifactKind.CISCO_IOS_RUNNING_CONFIG,
        content_type="text/plain",
        size_bytes=len(content),
        sha256_checksum=hashlib.sha256(content).hexdigest(),
        storage_key="artifacts/1/versions/1/original",
    )


def test_parsers_do_not_import_database_or_api_frameworks() -> None:
    for module_path in _PARSER_MODULES:
        tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
        imported_roots = {
            alias.name.split(".", maxsplit=1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            (node.module or "").split(".", maxsplit=1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        assert not imported_roots & _FORBIDDEN_IMPORT_ROOTS, module_path


@pytest.mark.asyncio
async def test_verified_artifact_flows_through_real_ingestion_and_extraction_services() -> None:
    content = b"hostname router-01\ninterface GigabitEthernet0/1\n no shutdown\n"
    artifact, version = records(content)
    repository = MemoryRepository(artifact, version)
    storage = MemoryStorage(content)
    service = ExtractionService(
        repository=repository,
        ingestion_service=IngestionService(
            repository=repository,
            registry=build_default_adapter_registry(),
        ),
        content_reader=ArtifactContentReader(storage=storage, read_chunk_size_bytes=11),
    )

    result = await service.extract(artifact.id, version.version_number)

    assert repository.status_updates == [ArtifactStatus.PROCESSING, ArtifactStatus.PROCESSED]
    assert storage.storage_keys == [version.storage_key]
    assert result.extractor_name == "cisco_ios_running_config_parser"
    assert result.artifact_checksum == version.sha256_checksum
    assert [proposal.entity_type for proposal in result.entity_proposals] == [
        EntityType.DEVICE,
        EntityType.INTERFACE,
    ]
    assert result.relationship_proposals
    assert all(
        evidence.source_artifact_checksum == version.sha256_checksum
        for proposal in (*result.entity_proposals, *result.relationship_proposals)
        for evidence in proposal.evidence
    )
