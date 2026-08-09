"""Streaming checksum and temporary-storage support for artifact uploads."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterable
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

DEFAULT_UPLOAD_CHUNK_SIZE_BYTES = 64 * 1024


@dataclass(frozen=True)
class TemporaryArtifact:
    """A completed, temporary artifact file with verified byte metadata."""

    path: Path
    sha256_checksum: str
    size_bytes: int

    def cleanup(self) -> None:
        """Remove the temporary file once it has been finalized or abandoned."""
        self.path.unlink(missing_ok=True)


class ArtifactStreamProcessor:
    """Stream artifact chunks to temporary storage while calculating SHA-256."""

    def __init__(self, maximum_size_bytes: int, temporary_directory: Path | None = None) -> None:
        if maximum_size_bytes <= 0:
            raise ValueError("maximum_size_bytes must be positive.")
        self._maximum_size_bytes = maximum_size_bytes
        self._temporary_directory = temporary_directory

    async def process(self, chunks: AsyncIterable[bytes]) -> TemporaryArtifact:
        """Write chunks once, enforcing size and returning checksum plus byte count."""
        digest = hashlib.sha256()
        size_bytes = 0
        temporary_path: Path | None = None

        try:
            with NamedTemporaryFile(
                mode="wb",
                prefix="egp-artifact-",
                suffix=".tmp",
                dir=self._temporary_directory,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                async for chunk in chunks:
                    if not isinstance(chunk, bytes):
                        raise ValueError("artifact stream chunks must be bytes.")
                    size_bytes += len(chunk)
                    if size_bytes > self._maximum_size_bytes:
                        raise ValueError("artifact content exceeds the configured maximum size.")
                    digest.update(chunk)
                    temporary_file.write(chunk)

            if size_bytes == 0:
                raise ValueError("artifact content must not be empty.")

            return TemporaryArtifact(
                path=temporary_path,
                sha256_checksum=digest.hexdigest(),
                size_bytes=size_bytes,
            )
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise
