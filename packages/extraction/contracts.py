"""Framework-independent content contracts for deterministic extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ReadableArtifactStream(Protocol):
    """Read-only asynchronous bytes from trusted internal object storage."""

    async def read(self, size: int = -1) -> bytes:
        """Read up to ``size`` bytes from the immutable source object."""


class ArtifactContentStorage(Protocol):
    """Internal storage access used only with a persisted trusted storage key."""

    async def open_original(self, *, storage_key: str) -> ReadableArtifactStream:
        """Open the original immutable bytes for internal read-only use."""


@dataclass(frozen=True, slots=True)
class VerifiedArtifactText:
    """UTF-8 source text verified against immutable artifact-version metadata."""

    text: str
    byte_count: int
