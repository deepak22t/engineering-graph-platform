"""Central typed-property metadata used by semantic compilation stages."""

from __future__ import annotations

from packages.domain.entities.properties import (
    ComponentProperties,
    ConnectionProperties,
    ContainerProperties,
    DeviceProperties,
    FirewallProperties,
    InterfaceProperties,
    IPAddressProperties,
    NetworkProperties,
    RouteProperties,
    ServiceProperties,
    SiteProperties,
    VlanProperties,
)
from packages.domain.enums import EntityType

PROPERTY_MODELS = {
    EntityType.DEVICE: DeviceProperties,
    EntityType.COMPONENT: ComponentProperties,
    EntityType.INTERFACE: InterfaceProperties,
    EntityType.NETWORK: NetworkProperties,
    EntityType.SITE: SiteProperties,
    EntityType.SERVICE: ServiceProperties,
    EntityType.CONTAINER: ContainerProperties,
    EntityType.IP: IPAddressProperties,
    EntityType.VLAN: VlanProperties,
    EntityType.ROUTE: RouteProperties,
    EntityType.FIREWALL: FirewallProperties,
    EntityType.CONNECTION: ConnectionProperties,
}


def is_canonical_property_path(entity_type: EntityType, field_path: str) -> bool:
    """Return whether a field path names a typed canonical property."""

    prefix, separator, property_name = field_path.partition(".")
    return (
        prefix == "properties"
        and separator == "."
        and bool(property_name)
        and property_name in PROPERTY_MODELS[entity_type].model_fields
        and property_name != "extensions"
    )


__all__ = ["PROPERTY_MODELS", "is_canonical_property_path"]
