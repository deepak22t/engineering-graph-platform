"""Deterministic classification for supported text artifacts."""

from pathlib import Path

from packages.artifacts.contracts import ArtifactKind


class ArtifactClassifier:
    """Classify an artifact without extracting engineering facts."""

    @classmethod
    def classify_text(cls, text: str, *, filename: str | None = None) -> ArtifactKind:
        """Return exactly one approved kind or reject unknown and ambiguous text."""
        if not isinstance(text, str):
            raise ValueError("artifact text must be a string.")
        return cls._classify(
            markers=cls._markers_from_lines(text.splitlines()), filename=filename
        )

    @classmethod
    def classify_file(cls, path: Path, *, filename: str | None = None) -> ArtifactKind:
        """Classify a UTF-8 temporary file without loading it all into memory."""
        try:
            with path.open("r", encoding="utf-8") as artifact_file:
                return cls._classify(
                    markers=cls._markers_from_lines(artifact_file),
                    filename=filename or path.name,
                )
        except UnicodeDecodeError as error:
            raise ValueError("artifact content must be valid UTF-8 text.") from error

    @classmethod
    def _markers_from_lines(cls, lines) -> set[str]:
        markers: set[str] = set()
        for line in lines:
            normalized = line.casefold()
            for marker in cls._all_markers():
                if marker in normalized:
                    markers.add(marker)
        return markers

    @staticmethod
    def _all_markers() -> tuple[str, ...]:
        return (
            "version ",
            "hostname ",
            "interface ",
            "device id:",
            "interface:",
            "port id",
            "port id:",
            "local intf:",
            "local interface:",
            "chassis id:",
            "system name:",
        )

    @classmethod
    def _classify(cls, *, markers: set[str], filename: str | None) -> ArtifactKind:
        matches = [
            kind
            for kind, is_match in (
                (ArtifactKind.CISCO_IOS_RUNNING_CONFIG, cls._is_running_config(markers)),
                (ArtifactKind.CDP_NEIGHBORS_DETAIL, cls._is_cdp_neighbors_detail(markers)),
                (ArtifactKind.LLDP_NEIGHBORS_DETAIL, cls._is_lldp_neighbors_detail(markers)),
            )
            if is_match
        ]
        if len(matches) > 1:
            raise ValueError(
                "text matches multiple artifact kinds and cannot be classified safely."
            )
        if matches:
            return matches[0]
        return cls._classify_explicit_format(filename)

    @staticmethod
    def _classify_explicit_format(filename: str | None) -> ArtifactKind:
        if filename is None:
            raise ValueError("text is not a supported artifact format.")

        kind_by_extension = {
            ".json": ArtifactKind.JSON,
            ".yaml": ArtifactKind.YAML,
            ".yml": ArtifactKind.YAML,
            ".csv": ArtifactKind.CSV,
            ".txt": ArtifactKind.TEXT,
        }
        try:
            return kind_by_extension[Path(filename).suffix.casefold()]
        except KeyError as error:
            raise ValueError("text is not a supported artifact format.") from error

    @staticmethod
    def _is_running_config(markers: set[str]) -> bool:
        return all(marker in markers for marker in ("version ", "hostname ", "interface "))

    @staticmethod
    def _is_cdp_neighbors_detail(markers: set[str]) -> bool:
        return all(marker in markers for marker in ("device id:", "interface:", "port id"))

    @staticmethod
    def _is_lldp_neighbors_detail(markers: set[str]) -> bool:
        has_local_interface = "local intf:" in markers or "local interface:" in markers
        has_identity = "chassis id:" in markers or "system name:" in markers
        return has_local_interface and has_identity and "port id:" in markers
