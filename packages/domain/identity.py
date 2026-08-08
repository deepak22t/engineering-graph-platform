"""Typed, normalized canonical identity keys for graph entities.

Display names and mutable attributes are intentionally excluded from identity.
Each identity is scope-aware and serializes deterministically for UUIDv5 generation.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from packages.domain.enums import EntityType
from packages.domain.normalization import (
    normalize_cidr,
    normalize_hostname,
    normalize_interface_name,
    normalize_ip_address,
    normalize_text,
    normalize_vlan_id,
)
from packages.domain.scope import GraphScope


class BaseEntityIdentity(BaseModel):
    """Shared immutable identity contract for every canonical entity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_type: EntityType
    scope: GraphScope
    identity_version: int = Field(default=1, ge=1)

    @computed_field(return_type=dict[str, str | int])
    @property
    def identity_fields(self) -> dict[str, str | int]:
        """Return only the normalized natural-key fields for this entity type."""
        return self._identity_fields()

    def _identity_fields(self) -> dict[str, str | int]:
        raise NotImplementedError

    def canonical_serialization(self) -> str:
        """Return the stable serialized key used as UUIDv5 input."""
        payload = {
            "entity_type": self.entity_type.value,
            "identity_version": self.identity_version,
            "scope": self.scope.model_dump(mode="json"),
            "identity_fields": self.identity_fields,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class DeviceIdentity(BaseEntityIdentity):
    """Device identity: scoped serial number, or scoped site and hostname."""

    entity_type: Literal[EntityType.DEVICE] = EntityType.DEVICE
    serial_number: str | None = Field(default=None, max_length=255)
    hostname: str | None = Field(default=None, max_length=255)

    @field_validator("serial_number")
    @classmethod
    def normalize_serial_number(cls, value: str | None) -> str | None:
        return normalize_text(value) if value is not None else None

    @field_validator("hostname")
    @classmethod
    def normalize_hostname_value(cls, value: str | None) -> str | None:
        return normalize_hostname(value) if value is not None else None

    @model_validator(mode="after")
    def require_device_natural_key(self) -> "DeviceIdentity":
        if self.serial_number is not None:
            return self
        if self.hostname is None:
            raise ValueError("Device identity requires a serial number or hostname.")
        if self.scope.site_id is None:
            raise ValueError("Hostname-based device identity requires scope.site_id.")
        return self

    def _identity_fields(self) -> dict[str, str | int]:
        if self.serial_number is not None:
            return {"serial_number": self.serial_number}
        return {"hostname": self.hostname or ""}


class ComponentIdentity(BaseEntityIdentity):
    """Component identity within its parent device."""

    entity_type: Literal[EntityType.COMPONENT] = EntityType.COMPONENT
    parent_device_identity: DeviceIdentity
    component_locator: str = Field(min_length=1, max_length=255)
    serial_number: str | None = Field(default=None, max_length=255)

    @field_validator("component_locator", "serial_number")
    @classmethod
    def normalize_component_text(cls, value: str | None) -> str | None:
        return normalize_text(value) if value is not None else None

    @model_validator(mode="after")
    def require_matching_scope(self) -> "ComponentIdentity":
        if self.parent_device_identity.scope != self.scope:
            raise ValueError("Component and parent device scopes must match.")
        return self

    def _identity_fields(self) -> dict[str, str | int]:
        fields: dict[str, str | int] = {
            "parent_device_identity": self.parent_device_identity.canonical_serialization(),
            "component_locator": self.component_locator,
        }
        if self.serial_number is not None:
            fields["serial_number"] = self.serial_number
        return fields


class InterfaceIdentity(BaseEntityIdentity):
    """Interface identity within its owning device."""

    entity_type: Literal[EntityType.INTERFACE] = EntityType.INTERFACE
    parent_device_identity: DeviceIdentity
    interface_name: str = Field(min_length=1, max_length=255)

    @field_validator("interface_name")
    @classmethod
    def normalize_interface_name(cls, value: str) -> str:
        return normalize_interface_name(value)

    @model_validator(mode="after")
    def require_matching_scope(self) -> "InterfaceIdentity":
        if self.parent_device_identity.scope != self.scope:
            raise ValueError("Interface and parent device scopes must match.")
        return self

    def _identity_fields(self) -> dict[str, str | int]:
        return {
            "parent_device_identity": self.parent_device_identity.canonical_serialization(),
            "interface_name": self.interface_name,
        }


class NetworkIdentity(BaseEntityIdentity):
    """Network identity from scope and canonical CIDR."""

    entity_type: Literal[EntityType.NETWORK] = EntityType.NETWORK
    cidr: str = Field(min_length=1, max_length=64)

    @field_validator("cidr")
    @classmethod
    def normalize_cidr(cls, value: str) -> str:
        return normalize_cidr(value)

    def _identity_fields(self) -> dict[str, str | int]:
        return {"cidr": self.cidr}


class SiteIdentity(BaseEntityIdentity):
    """Site identity from organization scope and canonical code or name."""

    entity_type: Literal[EntityType.SITE] = EntityType.SITE
    site_code: str | None = Field(default=None, max_length=255)
    site_name: str | None = Field(default=None, max_length=255)

    @field_validator("site_code", "site_name")
    @classmethod
    def normalize_site_text(cls, value: str | None) -> str | None:
        return normalize_text(value) if value is not None else None

    @model_validator(mode="after")
    def require_site_code_or_name(self) -> "SiteIdentity":
        if self.site_code is None and self.site_name is None:
            raise ValueError("Site identity requires a canonical site code or name.")
        return self

    def _identity_fields(self) -> dict[str, str | int]:
        if self.site_code is not None:
            return {"site_code": self.site_code}
        return {"site_name": self.site_name or ""}


class ServiceIdentity(BaseEntityIdentity):
    """Service identity from scope, name, and namespace or application."""

    entity_type: Literal[EntityType.SERVICE] = EntityType.SERVICE
    service_name: str = Field(min_length=1, max_length=255)
    namespace: str | None = Field(default=None, max_length=255)
    application: str | None = Field(default=None, max_length=255)

    @field_validator("service_name", "namespace", "application")
    @classmethod
    def normalize_service_text(cls, value: str | None) -> str | None:
        return normalize_text(value) if value is not None else None

    @model_validator(mode="after")
    def require_service_context(self) -> "ServiceIdentity":
        if self.namespace is None and self.application is None:
            raise ValueError("Service identity requires a namespace or application.")
        return self

    def _identity_fields(self) -> dict[str, str | int]:
        fields: dict[str, str | int] = {"service_name": self.service_name}
        if self.namespace is not None:
            fields["namespace"] = self.namespace
        if self.application is not None:
            fields["application"] = self.application
        return fields


class ContainerIdentity(BaseEntityIdentity):
    """Container/workload identity within a cluster namespace."""

    entity_type: Literal[EntityType.CONTAINER] = EntityType.CONTAINER
    cluster: str = Field(min_length=1, max_length=255)
    namespace: str = Field(min_length=1, max_length=255)
    workload_id: str = Field(min_length=1, max_length=255)

    @field_validator("cluster", "namespace", "workload_id")
    @classmethod
    def normalize_container_text(cls, value: str) -> str:
        return normalize_text(value)

    def _identity_fields(self) -> dict[str, str | int]:
        return {
            "cluster": self.cluster,
            "namespace": self.namespace,
            "workload_id": self.workload_id,
        }


class IPIdentity(BaseEntityIdentity):
    """IP identity from scope, containing network, and canonical host address."""

    entity_type: Literal[EntityType.IP] = EntityType.IP
    network_identity: NetworkIdentity
    address: str = Field(min_length=1, max_length=64)

    @field_validator("address")
    @classmethod
    def normalize_address(cls, value: str) -> str:
        return normalize_ip_address(value)

    @model_validator(mode="after")
    def require_matching_scope(self) -> "IPIdentity":
        if self.network_identity.scope != self.scope:
            raise ValueError("IP address and network scopes must match.")
        return self

    def _identity_fields(self) -> dict[str, str | int]:
        return {
            "network_identity": self.network_identity.canonical_serialization(),
            "address": self.address,
        }


class VlanIdentity(BaseEntityIdentity):
    """VLAN identity from scope/site/network context and numeric VLAN ID."""

    entity_type: Literal[EntityType.VLAN] = EntityType.VLAN
    vlan_id: int = Field(ge=1, le=4094)

    @field_validator("vlan_id", mode="before")
    @classmethod
    def normalize_vlan(cls, value: int | str) -> int:
        return normalize_vlan_id(value)

    network_identity: NetworkIdentity | None = None

    @model_validator(mode="after")
    def require_vlan_context(self) -> "VlanIdentity":
        if self.network_identity is not None and self.network_identity.scope != self.scope:
            raise ValueError("VLAN and network scopes must match.")
        if self.scope.site_id is None and self.network_identity is None:
            raise ValueError("VLAN identity requires scope.site_id or a network identity.")
        return self

    def _identity_fields(self) -> dict[str, str | int]:
        fields: dict[str, str | int] = {"vlan_id": self.vlan_id}
        if self.network_identity is not None:
            fields["network_identity"] = self.network_identity.canonical_serialization()
        return fields


class RouteIdentity(BaseEntityIdentity):
    """Route identity from source device, destination, next hop, and table."""

    entity_type: Literal[EntityType.ROUTE] = EntityType.ROUTE
    source_device_identity: DeviceIdentity
    destination_cidr: str = Field(min_length=1, max_length=64)
    next_hop: str = Field(min_length=1, max_length=64)
    route_table: str = Field(default="default", min_length=1, max_length=255)

    @field_validator("destination_cidr")
    @classmethod
    def normalize_destination(cls, value: str) -> str:
        return normalize_cidr(value)

    @field_validator("next_hop")
    @classmethod
    def normalize_next_hop(cls, value: str) -> str:
        return normalize_ip_address(value)

    @field_validator("route_table")
    @classmethod
    def normalize_route_table(cls, value: str) -> str:
        return normalize_text(value)

    @model_validator(mode="after")
    def require_matching_scope(self) -> "RouteIdentity":
        if self.source_device_identity.scope != self.scope:
            raise ValueError("Route and source device scopes must match.")
        return self

    def _identity_fields(self) -> dict[str, str | int]:
        return {
            "source_device_identity": self.source_device_identity.canonical_serialization(),
            "destination_cidr": self.destination_cidr,
            "next_hop": self.next_hop,
            "route_table": self.route_table,
        }


class FirewallIdentity(BaseEntityIdentity):
    """Firewall appliance or policy identity within a scope."""

    entity_type: Literal[EntityType.FIREWALL] = EntityType.FIREWALL
    firewall_kind: Literal["appliance", "policy"] = "appliance"
    serial_number: str | None = Field(default=None, max_length=255)
    appliance_name: str | None = Field(default=None, max_length=255)
    policy_id: str | None = Field(default=None, max_length=255)

    @field_validator("serial_number", "appliance_name", "policy_id")
    @classmethod
    def normalize_firewall_text(cls, value: str | None) -> str | None:
        return normalize_text(value) if value is not None else None

    @model_validator(mode="after")
    def require_firewall_key(self) -> "FirewallIdentity":
        if self.firewall_kind == "policy":
            if self.policy_id is None:
                raise ValueError("Firewall policy identity requires policy_id.")
            return self
        if self.serial_number is None and self.appliance_name is None:
            raise ValueError(
                "Firewall appliance identity requires serial number or appliance name."
            )
        return self

    def _identity_fields(self) -> dict[str, str | int]:
        fields: dict[str, str | int] = {"firewall_kind": self.firewall_kind}
        if self.firewall_kind == "policy":
            fields["policy_id"] = self.policy_id or ""
        elif self.serial_number is not None:
            fields["serial_number"] = self.serial_number
        else:
            fields["appliance_name"] = self.appliance_name or ""
        return fields


ConnectableEntityIdentity = Annotated[
    DeviceIdentity
    | ComponentIdentity
    | InterfaceIdentity
    | NetworkIdentity
    | SiteIdentity
    | ServiceIdentity
    | ContainerIdentity
    | IPIdentity
    | VlanIdentity
    | RouteIdentity
    | FirewallIdentity,
    Field(discriminator="entity_type"),
]


class ConnectionIdentity(BaseEntityIdentity):
    """Connection identity from typed, normalized endpoint identities."""

    entity_type: Literal[EntityType.CONNECTION] = EntityType.CONNECTION
    endpoint_a_identity: ConnectableEntityIdentity
    endpoint_b_identity: ConnectableEntityIdentity
    connection_type: str = Field(min_length=1, max_length=255)

    @field_validator("connection_type")
    @classmethod
    def normalize_connection_type(cls, value: str) -> str:
        return normalize_text(value)

    @model_validator(mode="after")
    def validate_connection_endpoints(self) -> "ConnectionIdentity":
        if self.endpoint_a_identity.scope != self.scope:
            raise ValueError("Connection and first endpoint scopes must match.")
        if self.endpoint_b_identity.scope != self.scope:
            raise ValueError("Connection and second endpoint scopes must match.")
        first_endpoint = self.endpoint_a_identity.canonical_serialization()
        second_endpoint = self.endpoint_b_identity.canonical_serialization()
        if first_endpoint == second_endpoint:
            raise ValueError("Connection endpoints must be different.")
        return self

    def _identity_fields(self) -> dict[str, str | int]:
        first, second = sorted(
            (
                self.endpoint_a_identity.canonical_serialization(),
                self.endpoint_b_identity.canonical_serialization(),
            )
        )
        return {
            "endpoint_a_identity": first,
            "endpoint_b_identity": second,
            "connection_type": self.connection_type,
        }


EntityIdentity = Annotated[
    DeviceIdentity
    | ComponentIdentity
    | InterfaceIdentity
    | NetworkIdentity
    | SiteIdentity
    | ServiceIdentity
    | ContainerIdentity
    | IPIdentity
    | VlanIdentity
    | RouteIdentity
    | FirewallIdentity
    | ConnectionIdentity,
    Field(discriminator="entity_type"),
]
