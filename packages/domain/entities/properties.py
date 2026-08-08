"""Typed engineering property models for canonical entities."""

from __future__ import annotations

import ipaddress
from enum import Enum

from pydantic import Field, field_validator, model_validator

from packages.domain.entities.base import EntityProperties
from packages.domain.normalization import (
    normalize_cidr,
    normalize_interface_name,
    normalize_ip_address,
    normalize_mac_address,
    normalize_text,
    normalize_vlan_id,
)


class AddressFamily(str, Enum):
    IPV4 = "ipv4"
    IPV6 = "ipv6"


class LinkStatus(str, Enum):
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"


class DeviceProperties(EntityProperties):
    hostname: str = Field(min_length=1, max_length=255)
    vendor: str | None = Field(default=None, max_length=255)
    model: str | None = Field(default=None, max_length=255)
    serial_number: str | None = Field(default=None, max_length=255)
    device_role: str | None = Field(default=None, max_length=100)
    management_ip: str | None = None
    operating_system: str | None = Field(default=None, max_length=255)

    @field_validator(
        "hostname", "vendor", "model", "serial_number", "device_role", "operating_system"
    )
    @classmethod
    def normalize_text_fields(cls, value: str | None) -> str | None:
        return normalize_text(value) if value is not None else None

    @field_validator("management_ip")
    @classmethod
    def validate_management_ip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_ip_address(value)


class ComponentProperties(EntityProperties):
    component_type: str = Field(min_length=1, max_length=100)
    slot: str | None = Field(default=None, max_length=255)
    module: str | None = Field(default=None, max_length=255)
    serial_number: str | None = Field(default=None, max_length=255)

    @field_validator("component_type", "slot", "module", "serial_number")
    @classmethod
    def normalize_fields(cls, value: str | None) -> str | None:
        return normalize_text(value) if value is not None else None


class InterfaceProperties(EntityProperties):
    interface_name: str = Field(min_length=1, max_length=255)
    interface_type: str = Field(min_length=1, max_length=100)
    mac_address: str | None = None
    admin_status: LinkStatus = LinkStatus.UNKNOWN
    operational_status: LinkStatus = LinkStatus.UNKNOWN
    speed_bps: int | None = Field(default=None, gt=0)
    mtu: int | None = Field(default=None, ge=576, le=9216)

    @field_validator("interface_name")
    @classmethod
    def normalize_interface(cls, value: str) -> str:
        return normalize_interface_name(value)

    @field_validator("interface_type")
    @classmethod
    def normalize_interface_type(cls, value: str) -> str:
        return normalize_text(value)

    @field_validator("mac_address")
    @classmethod
    def normalize_mac(cls, value: str | None) -> str | None:
        return normalize_mac_address(value) if value is not None else None


class NetworkProperties(EntityProperties):
    cidr: str = Field(min_length=1, max_length=64)
    address_family: AddressFamily
    network_type: str = Field(min_length=1, max_length=100)

    @field_validator("cidr")
    @classmethod
    def normalize_cidr(cls, value: str) -> str:
        return normalize_cidr(value)

    @field_validator("network_type")
    @classmethod
    def normalize_network_type(cls, value: str) -> str:
        return normalize_text(value)

    @model_validator(mode="after")
    def match_address_family(self) -> "NetworkProperties":
        expected = (
            AddressFamily.IPV4
            if ipaddress.ip_network(self.cidr).version == 4
            else AddressFamily.IPV6
        )
        if self.address_family != expected:
            raise ValueError("address_family must match cidr.")
        return self


class SiteProperties(EntityProperties):
    site_type: str = Field(min_length=1, max_length=100)
    region: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)

    @field_validator("site_type", "region", "address")
    @classmethod
    def normalize_fields(cls, value: str | None) -> str | None:
        return normalize_text(value, casefold=False) if value is not None else None


class ServiceProperties(EntityProperties):
    service_name: str = Field(min_length=1, max_length=255)
    service_type: str = Field(min_length=1, max_length=100)
    owner: str | None = Field(default=None, max_length=255)
    application: str | None = Field(default=None, max_length=255)

    @field_validator("service_name", "service_type", "owner", "application")
    @classmethod
    def normalize_fields(cls, value: str | None) -> str | None:
        return normalize_text(value) if value is not None else None


class ContainerProperties(EntityProperties):
    workload_name: str = Field(min_length=1, max_length=255)
    image: str = Field(min_length=1, max_length=500)
    runtime: str = Field(min_length=1, max_length=100)

    @field_validator("workload_name", "image", "runtime")
    @classmethod
    def normalize_fields(cls, value: str) -> str:
        return normalize_text(value)


class IPAddressProperties(EntityProperties):
    address: str
    address_family: AddressFamily

    @field_validator("address")
    @classmethod
    def normalize_address(cls, value: str) -> str:
        return normalize_ip_address(value)

    @model_validator(mode="after")
    def match_address_family(self) -> "IPAddressProperties":
        expected = (
            AddressFamily.IPV4
            if ipaddress.ip_address(self.address).version == 4
            else AddressFamily.IPV6
        )
        if self.address_family != expected:
            raise ValueError("address_family must match address.")
        return self


class VlanProperties(EntityProperties):
    vlan_id: int = Field(ge=1, le=4094)

    @field_validator("vlan_id", mode="before")
    @classmethod
    def normalize_vlan(cls, value: int | str) -> int:
        return normalize_vlan_id(value)

    vlan_name: str | None = Field(default=None, max_length=255)

    @field_validator("vlan_name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return normalize_text(value, casefold=False) if value is not None else None


class RouteProperties(EntityProperties):
    destination_cidr: str
    next_hop: str
    metric: int | None = Field(default=None, ge=0)
    protocol: str = Field(min_length=1, max_length=100)

    @field_validator("destination_cidr")
    @classmethod
    def normalize_destination(cls, value: str) -> str:
        return normalize_cidr(value)

    @field_validator("next_hop")
    @classmethod
    def normalize_next_hop(cls, value: str) -> str:
        return normalize_ip_address(value)

    @field_validator("protocol")
    @classmethod
    def normalize_protocol(cls, value: str) -> str:
        return normalize_text(value)


class FirewallProperties(EntityProperties):
    firewall_type: str = Field(min_length=1, max_length=100)
    vendor: str | None = Field(default=None, max_length=255)
    model: str | None = Field(default=None, max_length=255)
    policy_id: str | None = Field(default=None, max_length=255)

    @field_validator("firewall_type", "vendor", "model", "policy_id")
    @classmethod
    def normalize_fields(cls, value: str | None) -> str | None:
        return normalize_text(value) if value is not None else None


class ConnectionProperties(EntityProperties):
    connection_type: str = Field(min_length=1, max_length=100)
    medium: str | None = Field(default=None, max_length=100)
    capacity_bps: int | None = Field(default=None, gt=0)
    operational_status: LinkStatus = LinkStatus.UNKNOWN

    @field_validator("connection_type", "medium")
    @classmethod
    def normalize_fields(cls, value: str | None) -> str | None:
        return normalize_text(value) if value is not None else None
