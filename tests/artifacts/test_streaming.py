"""Tests for streamed artifact checksum and temporary storage."""

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from packages.artifacts import ArtifactStreamProcessor


async def stream_chunks(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


@pytest.mark.asyncio
async def test_processor_streams_to_temporary_file_and_calculates_sha256(tmp_path: Path):
    content = b"hostname router-01\ninterface GigabitEthernet0/1\n"
    processor = ArtifactStreamProcessor(maximum_size_bytes=1_024, temporary_directory=tmp_path)

    result = await processor.process(stream_chunks(content[:15], content[15:]))

    assert result.size_bytes == len(content)
    assert result.sha256_checksum == hashlib.sha256(content).hexdigest()
    assert result.path.read_bytes() == content
    result.cleanup()
    assert not result.path.exists()


@pytest.mark.asyncio
async def test_processor_removes_temporary_file_when_size_limit_is_exceeded(tmp_path: Path):
    processor = ArtifactStreamProcessor(maximum_size_bytes=10, temporary_directory=tmp_path)

    with pytest.raises(ValueError, match="configured maximum size"):
        await processor.process(stream_chunks(b"small", b"artifact"))

    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_processor_rejects_empty_stream_and_cleans_up(tmp_path: Path):
    processor = ArtifactStreamProcessor(maximum_size_bytes=1_024, temporary_directory=tmp_path)

    with pytest.raises(ValueError, match="must not be empty"):
        await processor.process(stream_chunks())

    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_processor_rejects_non_byte_chunks_and_cleans_up(tmp_path: Path):
    processor = ArtifactStreamProcessor(maximum_size_bytes=1_024, temporary_directory=tmp_path)

    async def invalid_stream() -> AsyncIterator[bytes]:
        yield b"valid"
        yield "not-bytes"  # type: ignore[misc]

    with pytest.raises(ValueError, match="must be bytes"):
        await processor.process(invalid_stream())

    assert list(tmp_path.iterdir()) == []


def test_processor_requires_positive_configured_maximum_size():
    with pytest.raises(ValueError, match="maximum_size_bytes"):
        ArtifactStreamProcessor(maximum_size_bytes=0)
