"""Phase 3 ingestion contracts and adapter implementations."""

from packages.ingestion.adapter_registry import AdapterRegistry
from packages.ingestion.defaults import build_default_adapter_registry
from packages.ingestion.errors import (
    AdapterRegistryError,
    ArtifactNotFoundError,
    ArtifactVersionNotFoundError,
    ArtifactVersionNotReadyError,
    DuplicateAdapterRegistrationError,
    IngestionError,
    MissingArtifactStorageReferenceError,
    NoAdapterRegisteredError,
    UnsupportedArtifactKindError,
)
from packages.ingestion.models import ExtractionInput
from packages.ingestion.service import IngestionService

__all__ = [
    "AdapterRegistry",
    "AdapterRegistryError",
    "ArtifactNotFoundError",
    "ArtifactVersionNotFoundError",
    "ArtifactVersionNotReadyError",
    "build_default_adapter_registry",
    "DuplicateAdapterRegistrationError",
    "ExtractionInput",
    "IngestionError",
    "IngestionService",
    "MissingArtifactStorageReferenceError",
    "NoAdapterRegisteredError",
    "UnsupportedArtifactKindError",
]
