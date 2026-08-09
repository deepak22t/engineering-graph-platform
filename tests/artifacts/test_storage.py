"""Tests for immutable MinIO Artifact storage behavior."""

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from miniopy_async.error import S3Error

from packages.artifacts import (
    ArtifactVersionAlreadyStoredError,
    MinioArtifactStorage,
    TemporaryArtifact,
    artifact_storage_key,
)


class FakeMinioClient:
    def __init__(self):
        self.bucket_exists_value = False
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}

    async def bucket_exists(self, bucket_name: str) -> bool:
        return self.bucket_exists_value

    async def make_bucket(self, bucket_name: str) -> None:
        self.bucket_exists_value = True

    async def stat_object(self, bucket_name: str, object_name: str):
        if (bucket_name, object_name) not in self.objects:
            raise S3Error("NoSuchKey", "missing", None, None, None, SimpleNamespace())
        return SimpleNamespace()

    async def put_object(self, bucket_name, object_name, data, length, content_type):
        self.objects[(bucket_name, object_name)] = (data.read(), content_type)

    async def get_object(self, bucket_name: str, object_name: str):
        return self.objects[(bucket_name, object_name)]


def temporary_artifact(
    tmp_path: Path, content: bytes = b"router configuration"
) -> TemporaryArtifact:
    path = tmp_path / "upload.tmp"
    path.write_bytes(content)
    return TemporaryArtifact(path=path, sha256_checksum="a" * 64, size_bytes=len(content))


def test_storage_key_uses_ids_not_filename():
    artifact_id = UUID(int=1)
    assert artifact_storage_key(artifact_id, 2) == f"artifacts/{artifact_id}/versions/2/original"
    with pytest.raises(ValueError):
        artifact_storage_key(artifact_id, 0)


@pytest.mark.asyncio
async def test_store_original_creates_bucket_and_preserves_original_bytes(tmp_path: Path):
    client = FakeMinioClient()
    storage = MinioArtifactStorage(client, "engineering-artifacts")
    artifact_id = UUID(int=1)
    temporary = temporary_artifact(tmp_path, b"original\x00bytes")

    key = await storage.store_original(
        artifact_id=artifact_id,
        version_number=1,
        temporary_artifact=temporary,
        content_type="text/plain",
    )

    assert client.bucket_exists_value
    assert key == artifact_storage_key(artifact_id, 1)
    assert client.objects[("engineering-artifacts", key)] == (b"original\x00bytes", "text/plain")
    assert await storage.open_original(storage_key=key) == (
        b"original\x00bytes",
        "text/plain",
    )


@pytest.mark.asyncio
async def test_store_original_rejects_overwrite_of_existing_version(tmp_path: Path):
    client = FakeMinioClient()
    storage = MinioArtifactStorage(client, "engineering-artifacts")
    artifact_id = UUID(int=1)
    temporary = temporary_artifact(tmp_path)

    await storage.store_original(
        artifact_id=artifact_id,
        version_number=1,
        temporary_artifact=temporary,
        content_type="text/plain",
    )
    with pytest.raises(ArtifactVersionAlreadyStoredError):
        await storage.store_original(
            artifact_id=artifact_id,
            version_number=1,
            temporary_artifact=temporary,
            content_type="text/plain",
        )


@pytest.mark.asyncio
async def test_store_original_rejects_missing_or_changed_temporary_file(tmp_path: Path):
    storage = MinioArtifactStorage(FakeMinioClient(), "engineering-artifacts")
    missing = TemporaryArtifact(
        path=tmp_path / "missing.tmp", sha256_checksum="a" * 64, size_bytes=1
    )
    with pytest.raises(ValueError, match="does not exist"):
        await storage.store_original(
            artifact_id=UUID(int=1),
            version_number=1,
            temporary_artifact=missing,
            content_type="text/plain",
        )

    changed = temporary_artifact(tmp_path, b"changed")
    with pytest.raises(ValueError, match="does not match"):
        await storage.store_original(
            artifact_id=UUID(int=1),
            version_number=1,
            temporary_artifact=TemporaryArtifact(
                path=changed.path,
                sha256_checksum=changed.sha256_checksum,
                size_bytes=changed.size_bytes + 1,
            ),
            content_type="text/plain",
        )


def test_storage_requires_non_blank_bucket_name():
    with pytest.raises(ValueError, match="bucket_name"):
        MinioArtifactStorage(FakeMinioClient(), "   ")


def test_storage_key_cannot_include_an_unsafe_original_filename():
    unsafe_filename = "../../router-01; DROP TABLE artifacts.cfg"
    storage_key = artifact_storage_key(UUID(int=1), 1)

    assert unsafe_filename not in storage_key
    assert storage_key == "artifacts/00000000-0000-0000-0000-000000000001/versions/1/original"
