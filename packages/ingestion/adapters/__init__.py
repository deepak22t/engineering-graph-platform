"""Adapter contracts and declared deterministic-ingestion adapters."""

from packages.ingestion.adapters.base import IngestionAdapter
from packages.ingestion.adapters.declared import (
    CdpNeighborDetailAdapter,
    CiscoIosConfigAdapter,
    CsvAdapter,
    JsonAdapter,
    LldpNeighborDetailAdapter,
    TextAdapter,
    YamlAdapter,
)

__all__ = [
    "CdpNeighborDetailAdapter",
    "CiscoIosConfigAdapter",
    "CsvAdapter",
    "IngestionAdapter",
    "JsonAdapter",
    "LldpNeighborDetailAdapter",
    "TextAdapter",
    "YamlAdapter",
]
