"""Read, verify, and decode immutable text artifacts for deterministic extraction."""

from __future__ import annotations

import hashlib
import inspect

from packages.extraction.contracts import (
    ArtifactContentStorage,
    ReadableArtifactStream,
    VerifiedArtifactText,
)
from packages.extraction.errors import (
    ArtifactChecksumMismatchError,
    ArtifactContentReadError,
    ArtifactTextDecodingError,
)
from packages.ingestion.models import ExtractionInput

READ_CHUNK_SIZE_BYTES = 64 * 1024


class ArtifactContentReader:
    """Return parser-safe text only after source bytes pass integrity verification."""

    def __init__(
        self,
        *,
        storage: ArtifactContentStorage,
        read_chunk_size_bytes: int = READ_CHUNK_SIZE_BYTES,
    ) -> None:
        if read_chunk_size_bytes <= 0:
            raise ValueError("read_chunk_size_bytes must be positive.")
        self._storage = storage
        self._read_chunk_size_bytes = read_chunk_size_bytes

    async def read_verified_text(self, extraction_input: ExtractionInput) -> VerifiedArtifactText:
        """Read one trusted artifact version, verify SHA-256, and decode UTF-8 text."""
        stream: ReadableArtifactStream | None = None
        try:
            stream = await self._storage.open_original(storage_key=extraction_input.storage_key)
            content, checksum = await self._read_all(stream)
        except (ArtifactChecksumMismatchError, ArtifactTextDecodingError):
            raise
        except Exception as error:
            raise ArtifactContentReadError(
                extraction_input.artifact_id,
                extraction_input.version_number,
            ) from error
        finally:
            if stream is not None:
                await self._close_stream(stream)

        if checksum != extraction_input.sha256_checksum:
            raise ArtifactChecksumMismatchError(
                extraction_input.artifact_id,
                extraction_input.version_number,
            )
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ArtifactTextDecodingError(
                extraction_input.artifact_id,
                extraction_input.version_number,
            ) from error
        return VerifiedArtifactText(text=text, byte_count=len(content))

    async def _read_all(self, stream: ReadableArtifactStream) -> tuple[bytearray, str]:
        content = bytearray()
        digest = hashlib.sha256()
        while chunk := await stream.read(self._read_chunk_size_bytes):
            if not isinstance(chunk, bytes):
                raise TypeError("artifact content stream must return bytes.")
            digest.update(chunk)
            content.extend(chunk)
        return content, digest.hexdigest()

    @staticmethod
    async def _close_stream(stream: ReadableArtifactStream) -> None:
        close = getattr(stream, "close", None)
        if close is None:
            return
        result = close()
        if inspect.isawaitable(result):
            await result
