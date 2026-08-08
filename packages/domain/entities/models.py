"""Per-type canonical entity models."""

from __future__ import annotations

from pydantic import model_validator

from packages.domain.entities.base import CanonicalEntity
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
from packages.domain.identity import (
    ComponentIdentity,
    ConnectionIdentity,
    ContainerIdentity,
    DeviceIdentity,
    FirewallIdentity,
    InterfaceIdentity,
    IPIdentity,
    NetworkIdentity,
    RouteIdentity,
    ServiceIdentity,
    SiteIdentity,
    VlanIdentity,
)


class DeviceEntity(CanonicalEntity):
    identity: DeviceIdentity
    properties: DeviceProperties

    @model_validator(mode="after")
    def match_identity(self) -> "DeviceEntity":
        if (
            self.identity.hostname is not None
            and self.properties.hostname != self.identity.hostname
        ):
            raise ValueError("Device properties.hostname must match hostname identity.")
        if self.identity.serial_number is not None and self.properties.serial_number not in (
            None,
            self.identity.serial_number,
        ):
            raise ValueError("Device properties.serial_number conflicts with identity.")
        return self


class ComponentEntity(CanonicalEntity):
    identity: ComponentIdentity
    properties: ComponentProperties


class InterfaceEntity(CanonicalEntity):
    identity: InterfaceIdentity
    properties: InterfaceProperties

    @model_validator(mode="after")
    def match_identity(self) -> "InterfaceEntity":
        if self.properties.interface_name != self.identity.interface_name:
            raise ValueError("Interface properties.interface_name must match identity.")
        return self


class NetworkEntity(CanonicalEntity):
    identity: NetworkIdentity
    properties: NetworkProperties

    @model_validator(mode="after")
    def match_identity(self) -> "NetworkEntity":
        if self.properties.cidr != self.identity.cidr:
            raise ValueError("Network properties.cidr must match identity.")
        return self


class SiteEntity(CanonicalEntity):
    identity: SiteIdentity
    properties: SiteProperties


class ServiceEntity(CanonicalEntity):
    identity: ServiceIdentity
    properties: ServiceProperties


class ContainerEntity(CanonicalEntity):
    identity: ContainerIdentity
    properties: ContainerProperties


class IPAddressEntity(CanonicalEntity):
    identity: IPIdentity
    properties: IPAddressProperties

    @model_validator(mode="after")
    def match_identity(self) -> "IPAddressEntity":
        if self.properties.address != self.identity.address:
            raise ValueError("IP properties.address must match identity.")
        return self


class VlanEntity(CanonicalEntity):
    identity: VlanIdentity
    properties: VlanProperties

    @model_validator(mode="after")
    def match_identity(self) -> "VlanEntity":
        if self.properties.vlan_id != self.identity.vlan_id:
            raise ValueError("VLAN properties.vlan_id must match identity.")
        return self


class RouteEntity(CanonicalEntity):
    identity: RouteIdentity
    properties: RouteProperties

    @model_validator(mode="after")
    def match_identity(self) -> "RouteEntity":
        if self.properties.destination_cidr != self.identity.destination_cidr:
            raise ValueError("Route properties.destination_cidr must match identity.")
        if self.properties.next_hop != self.identity.next_hop:
            raise ValueError("Route properties.next_hop must match identity.")
        return self


class FirewallEntity(CanonicalEntity):
    identity: FirewallIdentity
    properties: FirewallProperties

    @model_validator(mode="after")
    def match_identity(self) -> "FirewallEntity":
        if (
            self.identity.firewall_kind == "policy"
            and self.properties.policy_id != self.identity.policy_id
        ):
            raise ValueError("Firewall policy properties.policy_id must match identity.")
        return self


class ConnectionEntity(CanonicalEntity):
    identity: ConnectionIdentity
    properties: ConnectionProperties

    @model_validator(mode="after")
    def match_identity(self) -> "ConnectionEntity":
        if self.properties.connection_type != self.identity.connection_type:
            raise ValueError("Connection properties.connection_type must match identity.")
        return self
