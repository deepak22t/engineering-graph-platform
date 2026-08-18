"""Declared adapters for the initial deterministic ingestion formats."""

from packages.artifacts.contracts import ArtifactKind
from packages.ingestion.adapters.base import IngestionAdapter


class CiscoIosConfigAdapter(IngestionAdapter):
    name = "cisco_ios_config"
    version = "1"

    def supports(self, artifact_kind: ArtifactKind) -> bool:
        return artifact_kind is ArtifactKind.CISCO_IOS_RUNNING_CONFIG


class CdpNeighborDetailAdapter(IngestionAdapter):
    name = "cdp_neighbor_detail"
    version = "1"

    def supports(self, artifact_kind: ArtifactKind) -> bool:
        return artifact_kind is ArtifactKind.CDP_NEIGHBORS_DETAIL


class LldpNeighborDetailAdapter(IngestionAdapter):
    name = "lldp_neighbor_detail"
    version = "1"

    def supports(self, artifact_kind: ArtifactKind) -> bool:
        return artifact_kind is ArtifactKind.LLDP_NEIGHBORS_DETAIL


class JsonAdapter(IngestionAdapter):
    name = "json"
    version = "1"

    def supports(self, artifact_kind: ArtifactKind) -> bool:
        return artifact_kind is ArtifactKind.JSON


class YamlAdapter(IngestionAdapter):
    name = "yaml"
    version = "1"

    def supports(self, artifact_kind: ArtifactKind) -> bool:
        return artifact_kind is ArtifactKind.YAML


class CsvAdapter(IngestionAdapter):
    name = "csv"
    version = "1"

    def supports(self, artifact_kind: ArtifactKind) -> bool:
        return artifact_kind is ArtifactKind.CSV


class TextAdapter(IngestionAdapter):
    name = "text"
    version = "1"

    def supports(self, artifact_kind: ArtifactKind) -> bool:
        return artifact_kind is ArtifactKind.TEXT
