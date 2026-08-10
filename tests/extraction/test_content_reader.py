"""Tests for verified internal artifact-content reads."""

import hashlib
from collections import deque
from uuid import UUID

import pytest

from packages.artifacts import ArtifactKind, ArtifactScope
from packages.extraction import (
    ArtifactChecksumMismatchError,
    ArtifactContentReader,
    ArtifactContentReadError,
    ArtifactTextDecodingError,
)
from packages.ingestion.models import ExtractionInput


class FakeStream:
    def __init__(self, chunks: list[bytes] | None = None, error: Exception | None = None) -> None:
        self._chunks = deque(chunks or [])
        self._error = error
        self.closed = False
        self.read_sizes: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if self._error is not None:
            raise self._error
        return self._chunks.popleft() if self._chunks else b""

    async def close(self) -> None:
        self.closed = True


class FakeStorage:
    def __init__(self, stream: FakeStream | None = None, error: Exception | None = None) -> None:
        self.stream = stream
        self.error = error
        self.storage_keys: list[str] = []

    async def open_original(self, *, storage_key: str) -> FakeStream:
        self.storage_keys.append(storage_key)
        if self.error is not None:
            raise self.error
        assert self.stream is not None
        return self.stream


def extraction_input(checksum: str) -> ExtractionInput:
    return ExtractionInput(
        artifact_id=UUID(int=1),
        artifact_version_id=UUID(int=2),
        version_number=3,
        scope=ArtifactScope(
            organization_id=UUID(int=4),
            project_id=UUID(int=5),
            environment="production",
            site_id=UUID(int=6),
        ),
        artifact_kind=ArtifactKind.CISCO_IOS_RUNNING_CONFIG,
        sha256_checksum=checksum,
        original_filename="ignored-by-reader.cfg",
        storage_key="artifacts/trusted/versions/3/original",
        adapter_name="cisco_ios_config",
        adapter_version="1",
    )


@pytest.mark.asyncio
async def test_reader_streams_verifies_and_decodes_original_text() -> None:
    content = b"hostname router-01\ninterface GigabitEthernet0/1\n"
    stream = FakeStream([content[:12], content[12:]])
    storage = FakeStorage(stream)
    reader = ArtifactContentReader(storage=storage, read_chunk_size_bytes=12)

    result = await reader.read_verified_text(extraction_input(hashlib.sha256(content).hexdigest()))

    assert result.text == content.decode("utf-8")
    assert result.byte_count == len(content)
    assert storage.storage_keys == ["artifacts/trusted/versions/3/original"]
    assert stream.read_sizes == [12, 12, 12]
    assert stream.closed


@pytest.mark.asyncio
async def test_reader_rejects_checksum_mismatch_and_closes_stream() -> None:
    stream = FakeStream([b"hostname router-01\n"])
    reader = ArtifactContentReader(storage=FakeStorage(stream))

    with pytest.raises(ArtifactChecksumMismatchError, match="version 3"):
        await reader.read_verified_text(extraction_input("a" * 64))

    assert stream.closed


@pytest.mark.asyncio
async def test_reader_rejects_invalid_utf8_and_closes_stream() -> None:
    content = b"hostname \xff\n"
    stream = FakeStream([content])
    reader = ArtifactContentReader(storage=FakeStorage(stream))

    with pytest.raises(ArtifactTextDecodingError, match="version 3"):
        await reader.read_verified_text(extraction_input(hashlib.sha256(content).hexdigest()))

    assert stream.closed


@pytest.mark.asyncio
async def test_reader_wraps_missing_or_unreadable_storage_object_safely() -> None:
    reader = ArtifactContentReader(storage=FakeStorage(error=FileNotFoundError("not exposed")))

    with pytest.raises(ArtifactContentReadError, match="could not read original content"):
        await reader.read_verified_text(extraction_input("a" * 64))


@pytest.mark.asyncio
async def test_reader_wraps_invalid_stream_chunks_safely() -> None:
    stream = FakeStream([b"valid"])
    stream._chunks.append("not-bytes")  # type: ignore[arg-type]
    reader = ArtifactContentReader(storage=FakeStorage(stream))

    with pytest.raises(ArtifactContentReadError, match="could not read original content"):
        await reader.read_verified_text(extraction_input(hashlib.sha256(b"valid").hexdigest()))

    assert stream.closed


def test_reader_requires_a_positive_chunk_size() -> None:
    with pytest.raises(ValueError, match="read_chunk_size_bytes"):
        ArtifactContentReader(storage=FakeStorage(), read_chunk_size_bytes=0)
