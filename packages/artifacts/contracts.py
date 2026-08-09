"""Minimal, framework-independent contracts for the Artifact Service."""

from enum import Enum
from uuid import UUID

from packages.domain.scope import GraphScope


class ArtifactKind(str, Enum):
    """The only artifact kinds accepted by the first Cisco topology vertical."""

    CISCO_IOS_RUNNING_CONFIG = "cisco_ios_running_config"
    CDP_NEIGHBORS_DETAIL = "cdp_neighbors_detail"
    LLDP_NEIGHBORS_DETAIL = "lldp_neighbors_detail"


class ArtifactStatus(str, Enum):
    """Lifecycle states required for artifact processing."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class ArtifactScope(GraphScope):
    """Mandatory location context for an uploaded Cisco topology artifact."""

    site_id: UUID
