"""Safe errors raised while reading immutable artifact content for extraction."""

from uuid import UUID


class ExtractionContentError(ValueError):
    """Base error for source-content retrieval and verification."""


class ArtifactContentReadError(ExtractionContentError):
    """Raised when the trusted original source object cannot be read."""

    def __init__(self, artifact_id: UUID, version_number: int) -> None:
        self.artifact_id = artifact_id
        self.version_number = version_number
        super().__init__(
            f"could not read original content for artifact {artifact_id} version {version_number}."
        )


class ArtifactChecksumMismatchError(ExtractionContentError):
    """Raised when stored original bytes no longer match immutable version metadata."""

    def __init__(self, artifact_id: UUID, version_number: int) -> None:
        self.artifact_id = artifact_id
        self.version_number = version_number
        super().__init__(f"checksum mismatch for artifact {artifact_id} version {version_number}.")


class ArtifactTextDecodingError(ExtractionContentError):
    """Raised when a text artifact cannot be decoded as valid UTF-8."""

    def __init__(self, artifact_id: UUID, version_number: int) -> None:
        self.artifact_id = artifact_id
        self.version_number = version_number
        super().__init__(
            f"artifact {artifact_id} version {version_number} is not valid UTF-8 text."
        )


class UnsupportedExtractionKindError(ValueError):
    """Raised when an artifact kind has no approved deterministic schema yet."""

    def __init__(self, artifact_kind: str) -> None:
        self.artifact_kind = artifact_kind
        super().__init__(
            f"Deterministic extraction is not implemented for artifact kind: {artifact_kind}."
        )
