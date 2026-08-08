"""Typed canonical entity domain package."""

from pydantic import BaseModel, ConfigDict, Field

from packages.domain.entities.base import (
    CanonicalEntity,
    EntityProperties,
    LifecycleState,
    ObservationState,
)
from packages.domain.entities.models import (
    ComponentEntity,
    ConnectionEntity,
    ContainerEntity,
    DeviceEntity,
    FirewallEntity,
    InterfaceEntity,
    IPAddressEntity,
    NetworkEntity,
    RouteEntity,
    ServiceEntity,
    SiteEntity,
    VlanEntity,
)
from packages.domain.entities.properties import (
    AddressFamily,
    ComponentProperties,
    ConnectionProperties,
    ContainerProperties,
    DeviceProperties,
    FirewallProperties,
    InterfaceProperties,
    IPAddressProperties,
    LinkStatus,
    NetworkProperties,
    RouteProperties,
    ServiceProperties,
    SiteProperties,
    VlanProperties,
)
from packages.domain.evidence import Confidence, Evidence

CanonicalEntityPayload = (
    DeviceEntity
    | ComponentEntity
    | InterfaceEntity
    | NetworkEntity
    | SiteEntity
    | ServiceEntity
    | ContainerEntity
    | IPAddressEntity
    | VlanEntity
    | RouteEntity
    | FirewallEntity
    | ConnectionEntity
)


class EvidenceBackedEntity(BaseModel):
    """A typed canonical entity with evidence and confidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity: CanonicalEntityPayload
    evidence: tuple[Evidence, ...] = Field(min_length=1)
    confidence: Confidence

    @property
    def id(self):
        return self.entity.id

    @property
    def entity_type(self):
        return self.entity.entity_type


# Compatibility alias; new code should use a concrete *Entity class.
Entity = CanonicalEntity

__all__ = [
    "AddressFamily",
    "CanonicalEntityPayload",
    "CanonicalEntity",
    "ComponentEntity",
    "ComponentProperties",
    "ConnectionEntity",
    "ConnectionProperties",
    "ContainerEntity",
    "ContainerProperties",
    "DeviceEntity",
    "DeviceProperties",
    "Entity",
    "EntityProperties",
    "EvidenceBackedEntity",
    "FirewallEntity",
    "FirewallProperties",
    "IPAddressEntity",
    "IPAddressProperties",
    "InterfaceEntity",
    "InterfaceProperties",
    "LifecycleState",
    "ObservationState",
    "LinkStatus",
    "NetworkEntity",
    "NetworkProperties",
    "RouteEntity",
    "RouteProperties",
    "ServiceEntity",
    "ServiceProperties",
    "SiteEntity",
    "SiteProperties",
    "VlanEntity",
    "VlanProperties",
]
