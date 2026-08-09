"""Tests for PostgreSQL Artifact metadata persistence."""

from contextlib import asynccontextmanager
from uuid import UUID

import pytest

from packages.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactScope,
    ArtifactVersion,
    PostgresArtifactRepository,
)


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple]] = []
        self.transaction_entered = False
        self.row = None

    async def execute(self, statement: str, *arguments) -> None:
        self.statements.append((statement, arguments))

    async def fetchrow(self, statement: str, *arguments):
        self.statements.append((statement, arguments))
        return self.row

    @asynccontextmanager
    async def transaction(self):
        self.transaction_entered = True
        yield


class FakePool:
    def __init__(self) -> None:
        self.connection = FakeConnection()

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


def records() -> tuple[Artifact, ArtifactVersion]:
    artifact = Artifact(
        id=UUID(int=1),
        scope=ArtifactScope(
            organization_id=UUID(int=2),
            project_id=UUID(int=3),
            environment="prod",
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
        size_bytes=10,
        sha256_checksum="a" * 64,
        storage_key="artifacts/00000000-0000-0000-0000-000000000001/versions/1/original",
    )


@pytest.mark.asyncio
async def test_initialize_schema_creates_only_artifact_tables():
    pool = FakePool()

    await PostgresArtifactRepository(pool).initialize_schema()

    assert len(pool.connection.statements) == 2
    assert "CREATE TABLE IF NOT EXISTS artifacts" in pool.connection.statements[0][0]
    assert "CREATE TABLE IF NOT EXISTS artifact_versions" in pool.connection.statements[1][0]


@pytest.mark.asyncio
async def test_initial_artifact_and_version_are_inserted_in_one_transaction():
    pool = FakePool()
    artifact, version = records()

    await PostgresArtifactRepository(pool).create_artifact_with_initial_version(artifact, version)

    assert pool.connection.transaction_entered
    assert len(pool.connection.statements) == 2
    assert "INSERT INTO artifacts" in pool.connection.statements[0][0]
    assert "INSERT INTO artifact_versions" in pool.connection.statements[1][0]
    assert pool.connection.statements[0][1][0] == artifact.id
    assert pool.connection.statements[1][1][1] == version.artifact_id
    assert pool.connection.statements[1][1][9] == "uploaded"


@pytest.mark.asyncio
async def test_get_version_returns_exact_immutable_metadata_or_none() -> None:
    pool = FakePool()
    _, version = records()
    pool.connection.row = version.model_dump()
    repository = PostgresArtifactRepository(pool)

    assert await repository.get_version(version.artifact_id, version.version_number) == version
    assert pool.connection.statements[-1][1] == (version.artifact_id, version.version_number)

    pool.connection.row = None
    assert await repository.get_version(version.artifact_id, 2) is None
