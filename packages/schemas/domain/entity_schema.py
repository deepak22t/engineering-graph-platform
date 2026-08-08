"""Safe API schemas for typed canonical entities."""

from datetime import datetime, timezone
from typing import TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from packages.domain.entities import (
    CanonicalEntity,
    ComponentEntity,
    ComponentProperties,
    ConnectionEntity,
    ConnectionProperties,
    ContainerEntity,
    ContainerProperties,
    DeviceEntity,
    DeviceProperties,
    FirewallEntity,
    FirewallProperties,
    InterfaceEntity,
    InterfaceProperties,
    IPAddressEntity,
    IPAddressProperties,
    NetworkEntity,
    NetworkProperties,
    RouteEntity,
    RouteProperties,
    ServiceEntity,
    ServiceProperties,
    SiteEntity,
    SiteProperties,
    VlanEntity,
    VlanProperties,
)
from packages.domain.enums import EntityType
from packages.domain.identity import EntityIdentity
from packages.domain.scope import GraphScope

EntityPropertiesPayload: TypeAlias = (
    DeviceProperties
    | ComponentProperties
    | InterfaceProperties
    | NetworkProperties
    | SiteProperties
    | ServiceProperties
    | ContainerProperties
    | IPAddressProperties
    | VlanProperties
    | RouteProperties
    | FirewallProperties
    | ConnectionProperties
)

_ENTITY_BY_TYPE = {
    EntityType.DEVICE: (DeviceEntity, DeviceProperties),
    EntityType.COMPONENT: (ComponentEntity, ComponentProperties),
    EntityType.INTERFACE: (InterfaceEntity, InterfaceProperties),
    EntityType.NETWORK: (NetworkEntity, NetworkProperties),
    EntityType.SITE: (SiteEntity, SiteProperties),
    EntityType.SERVICE: (ServiceEntity, ServiceProperties),
    EntityType.CONTAINER: (ContainerEntity, ContainerProperties),
    EntityType.IP: (IPAddressEntity, IPAddressProperties),
    EntityType.VLAN: (VlanEntity, VlanProperties),
    EntityType.ROUTE: (RouteEntity, RouteProperties),
    EntityType.FIREWALL: (FirewallEntity, FirewallProperties),
    EntityType.CONNECTION: (ConnectionEntity, ConnectionProperties),
}


class CreateEntityRequest(BaseModel):
    """Request that validates properties against the supplied typed identity."""

    model_config = ConfigDict(extra="forbid")

    identity: EntityIdentity
    display_name: str
    properties: EntityPropertiesPayload

    @model_validator(mode="after")
    def match_identity_and_properties(self) -> "CreateEntityRequest":
        _, expected_properties = _ENTITY_BY_TYPE[self.identity.entity_type]
        if type(self.properties) is not expected_properties:
            raise ValueError("Properties type must match identity.entity_type.")
        return self

    def to_entity(self) -> CanonicalEntity:
        """Create a fully typed canonical entity with server timestamps."""
        entity_class, _ = _ENTITY_BY_TYPE[self.identity.entity_type]
        now = datetime.now(timezone.utc)
        return entity_class(
            identity=self.identity,
            display_name=self.display_name,
            properties=self.properties,
            first_observed_at=now,
            last_observed_at=now,
            created_at=now,
            updated_at=now,
        )


class EntityResponse(BaseModel):
    """Serialized, typed canonical entity response."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    entity_type: EntityType
    identity: EntityIdentity
    scope: GraphScope
    display_name: str
    properties: EntityPropertiesPayload
    lifecycle_state: str
    first_observed_at: datetime
    last_observed_at: datetime
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, entity: CanonicalEntity) -> "EntityResponse":
        return cls(
            id=entity.id,
            entity_type=entity.entity_type,
            identity=entity.identity,
            scope=entity.scope,
            display_name=entity.display_name,
            properties=entity.properties,
            lifecycle_state=entity.lifecycle_state.value,
            first_observed_at=entity.first_observed_at,
            last_observed_at=entity.last_observed_at,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
