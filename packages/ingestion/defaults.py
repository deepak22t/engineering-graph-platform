"""Default adapter composition for the initial deterministic ingestion path."""

from packages.ingestion.adapter_registry import AdapterRegistry
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

DEFAULT_INGESTION_ADAPTERS: tuple[IngestionAdapter, ...] = (
    CiscoIosConfigAdapter(),
    CdpNeighborDetailAdapter(),
    LldpNeighborDetailAdapter(),
    JsonAdapter(),
    YamlAdapter(),
    CsvAdapter(),
    TextAdapter(),
)


def build_default_adapter_registry() -> AdapterRegistry:
    """Build the one explicit registry for the supported Phase 3 formats."""
    return AdapterRegistry(DEFAULT_INGESTION_ADAPTERS)
