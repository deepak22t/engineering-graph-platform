"""Safe validation for supported deterministic-ingestion text artifacts."""

from __future__ import annotations

from pathlib import Path, PurePath

from packages.artifacts.classification import ArtifactClassifier
from packages.artifacts.contracts import ArtifactKind


class ArtifactFileValidator:
    """Validate raw bytes or a temporary file before artifact storage."""

    _ALLOWED_EXTENSIONS = frozenset(
        {".txt", ".cfg", ".conf", ".cnf", ".json", ".yaml", ".yml", ".csv"}
    )
    _ALLOWED_APPLICATION_CONTENT_TYPES = frozenset(
        {"application/json", "application/yaml", "application/x-yaml"}
    )
    _BINARY_SIGNATURES = (
        b"%PDF-",
        b"\x89PNG\r\n\x1a\n",
        b"\xff\xd8\xff",
        b"PK\x03\x04",
        b"Rar!\x1a\x07",
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
        b"MZ",
        b"\x7fELF",
        b"AC10",
    )

    def __init__(self, maximum_size_bytes: int) -> None:
        if maximum_size_bytes <= 0:
            raise ValueError("maximum_size_bytes must be positive.")
        self._maximum_size_bytes = maximum_size_bytes

    def validate(self, *, filename: str, content_type: str, content: bytes) -> ArtifactKind:
        """Validate in-memory test bytes and return their approved artifact kind."""
        self._validate_filename(filename)
        self._validate_content_type(content_type)
        self._validate_size(len(content))
        self._reject_binary_signatures(content)
        text = self._decode_text(content)
        self._reject_binary_control_characters(text)
        return ArtifactClassifier.classify_text(text, filename=filename)

    def validate_file(
        self, *, filename: str, content_type: str, path: Path, size_bytes: int
    ) -> ArtifactKind:
        """Validate a temporary file without loading the full artifact into memory."""
        self._validate_filename(filename)
        self._validate_content_type(content_type)
        self._validate_size(size_bytes)
        if not path.is_file() or path.stat().st_size != size_bytes:
            raise ValueError("temporary artifact file does not match its metadata.")
        with path.open("rb") as artifact_file:
            self._reject_binary_signatures(
                artifact_file.read(max(map(len, self._BINARY_SIGNATURES)))
            )
        self._validate_text_file(path)
        return ArtifactClassifier.classify_file(path, filename=filename)

    def _validate_filename(self, filename: str) -> None:
        if not filename or not filename.strip():
            raise ValueError("filename must not be blank.")
        if "\x00" in filename or "/" in filename or "\\" in filename:
            raise ValueError("filename must not contain a path.")
        path = PurePath(filename)
        if path.name != filename or filename in {".", ".."}:
            raise ValueError("filename must be a plain file name.")
        if path.suffix and path.suffix.casefold() not in self._ALLOWED_EXTENSIONS:
            raise ValueError("filename extension is not supported for text artifacts.")

    @staticmethod
    def _validate_content_type(content_type: str) -> None:
        normalized = content_type.split(";", maxsplit=1)[0].strip().casefold()
        if normalized.startswith("text/") or normalized in (
            ArtifactFileValidator._ALLOWED_APPLICATION_CONTENT_TYPES
        ):
            return
        raise ValueError("content_type must be text-like.")

    def _validate_size(self, size_bytes: int) -> None:
        if size_bytes <= 0:
            raise ValueError("artifact content must not be empty.")
        if size_bytes > self._maximum_size_bytes:
            raise ValueError("artifact content exceeds the configured maximum size.")

    @classmethod
    def _reject_binary_signatures(cls, content: bytes) -> None:
        if any(content.startswith(signature) for signature in cls._BINARY_SIGNATURES):
            raise ValueError("binary artifact content is not supported.")

    @staticmethod
    def _decode_text(content: bytes) -> str:
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("artifact content must be valid UTF-8 text.") from error

    def _validate_text_file(self, path: Path) -> None:
        try:
            with path.open("r", encoding="utf-8") as artifact_file:
                for text in iter(lambda: artifact_file.read(64 * 1024), ""):
                    self._reject_binary_control_characters(text)
        except UnicodeDecodeError as error:
            raise ValueError("artifact content must be valid UTF-8 text.") from error

    @staticmethod
    def _reject_binary_control_characters(text: str) -> None:
        if any(ord(character) < 32 and character not in "\t\n\r" for character in text):
            raise ValueError("artifact content contains binary control characters.")
