"""PostgreSQL persistence for Artifact metadata and immutable versions."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from packages.artifacts.contracts import ArtifactKind, ArtifactScope, ArtifactStatus
from packages.artifacts.models import Artifact, ArtifactVersion

_CREATE_ARTIFACTS_TABLE = """
CREATE TABLE IF NOT EXISTS artifacts (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    environment TEXT NOT NULL,
    site_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
)
"""

_CREATE_ARTIFACT_VERSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS artifact_versions (
    id UUID PRIMARY KEY,
    artifact_id UUID NOT NULL REFERENCES artifacts(id),
    version_number INTEGER NOT NULL CHECK (version_number >= 1),
    original_filename TEXT NOT NULL,
    artifact_kind TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
    sha256_checksum CHAR(64) NOT NULL,
    storage_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('uploaded', 'processing', 'processed', 'failed')),
    uploaded_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (artifact_id, version_number)
)
"""

_VERSION_COLUMNS = """
id, artifact_id, version_number, original_filename, artifact_kind, content_type,
size_bytes, sha256_checksum, storage_key, status, uploaded_at, created_at, updated_at
"""


class ArtifactRepository(Protocol):
    """Persistence contract used by the upload workflow."""

    async def create_artifact_with_initial_version(
        self, artifact: Artifact, version: ArtifactVersion
    ) -> None:
        """Persist an Artifact and its first immutable version atomically."""

    async def get_artifact(self, artifact_id: UUID) -> Artifact | None:
        """Return an Artifact by its logical identifier."""

    async def get_latest_version(self, artifact_id: UUID) -> ArtifactVersion | None:
        """Return the newest persisted immutable version for an Artifact."""

    async def get_version(
        self, artifact_id: UUID, version_number: int
    ) -> ArtifactVersion | None:
        """Return one immutable ArtifactVersion by its logical version number."""

    async def update_version_status(
        self, artifact_id: UUID, version_number: int, status: ArtifactStatus
    ) -> None:
        """Update processing lifecycle status for one immutable artifact version."""

    async def create_version(self, version: ArtifactVersion) -> None:
        """Persist one already-stored, non-initial ArtifactVersion."""


class PostgresArtifactRepository:
    """Persist artifact metadata using an asyncpg connection pool."""

    def __init__(self, pool) -> None:
        self._pool = pool

    async def initialize_schema(self) -> None:
        """Create the minimal Artifact Service tables required by Phase 2."""
        async with self._pool.acquire() as connection:
            await connection.execute(_CREATE_ARTIFACTS_TABLE)
            await connection.execute(_CREATE_ARTIFACT_VERSIONS_TABLE)

    async def create_artifact_with_initial_version(
        self, artifact: Artifact, version: ArtifactVersion
    ) -> None:
        """Create both records in one database transaction."""
        async with self._pool.acquire() as connection, connection.transaction():
            await connection.execute(
                """
                INSERT INTO artifacts (
                    id, organization_id, project_id, environment, site_id, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                artifact.id,
                artifact.scope.organization_id,
                artifact.scope.project_id,
                artifact.scope.environment,
                artifact.scope.site_id,
                artifact.created_at,
            )
            await self._insert_version(connection, version)

    async def get_artifact(self, artifact_id: UUID) -> Artifact | None:
        """Return a logical Artifact, if it exists."""
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT id, organization_id, project_id, environment, site_id, created_at
                FROM artifacts WHERE id = $1
                """,
                artifact_id,
            )
        if row is None:
            return None
        return Artifact(
            id=row["id"],
            scope=ArtifactScope(
                organization_id=row["organization_id"],
                project_id=row["project_id"],
                environment=row["environment"],
                site_id=row["site_id"],
            ),
            created_at=row["created_at"],
        )

    async def get_version(
        self, artifact_id: UUID, version_number: int
    ) -> ArtifactVersion | None:
        """Return one immutable version by its logical version number."""
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                SELECT {_VERSION_COLUMNS}
                FROM artifact_versions
                WHERE artifact_id = $1 AND version_number = $2
                """,
                artifact_id,
                version_number,
            )
        return self._version_from_row(row) if row is not None else None

    async def get_latest_version(self, artifact_id: UUID) -> ArtifactVersion | None:
        """Return the latest immutable version by version number."""
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                SELECT {_VERSION_COLUMNS}
                FROM artifact_versions
                WHERE artifact_id = $1
                ORDER BY version_number DESC
                LIMIT 1
                """,
                artifact_id,
            )
        return self._version_from_row(row) if row is not None else None

    async def update_version_status(
        self, artifact_id: UUID, version_number: int, status: ArtifactStatus
    ) -> None:
        """Update processing lifecycle status for one immutable artifact version."""
        async with self._pool.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE artifact_versions
                SET status = $3, updated_at = NOW()
                WHERE artifact_id = $1 AND version_number = $2
                """,
                artifact_id,
                version_number,
                status.value,
            )
        if result == "UPDATE 0":
            raise ValueError(
                f"Artifact version {artifact_id}/{version_number} does not exist."
            )

    async def create_version(self, version: ArtifactVersion) -> None:
        """Persist a later version after its original object has been stored."""
        async with self._pool.acquire() as connection:
            await self._insert_version(connection, version)

    @staticmethod
    async def _insert_version(connection, version: ArtifactVersion) -> None:
        await connection.execute(
            """
            INSERT INTO artifact_versions (
                id, artifact_id, version_number, original_filename, artifact_kind,
                content_type, size_bytes, sha256_checksum, storage_key, status,
                uploaded_at, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
            )
            """,
            version.id,
            version.artifact_id,
            version.version_number,
            version.original_filename,
            version.artifact_kind.value,
            version.content_type,
            version.size_bytes,
            version.sha256_checksum,
            version.storage_key,
            version.status.value,
            version.uploaded_at,
            version.created_at,
            version.updated_at,
        )

    @staticmethod
    def _version_from_row(row) -> ArtifactVersion:
        return ArtifactVersion(
            id=row["id"],
            artifact_id=row["artifact_id"],
            version_number=row["version_number"],
            original_filename=row["original_filename"],
            artifact_kind=ArtifactKind(row["artifact_kind"]),
            content_type=row["content_type"],
            size_bytes=row["size_bytes"],
            sha256_checksum=row["sha256_checksum"],
            storage_key=row["storage_key"],
            status=ArtifactStatus(row["status"]),
            uploaded_at=row["uploaded_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
