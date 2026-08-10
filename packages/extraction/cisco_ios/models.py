"""Intermediate, line-aware claims emitted by the Cisco IOS running-config parser."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class CiscoIosLine:
    """One original configuration line with its immutable source position."""

    number: int
    raw: str
    content: str
    is_indented: bool


@dataclass(frozen=True, slots=True)
class HostnameClaim:
    line: CiscoIosLine
    hostname: str


@dataclass(frozen=True, slots=True)
class InterfaceClaim:
    line: CiscoIosLine
    interface_name: str
    interface_type: str


@dataclass(frozen=True, slots=True)
class InterfaceDescriptionClaim:
    line: CiscoIosLine
    interface_name: str
    interface_line_number: int
    description: str


@dataclass(frozen=True, slots=True)
class InterfaceIpv4AddressClaim:
    line: CiscoIosLine
    interface_name: str
    interface_line_number: int
    address: str
    netmask: str
    network_cidr: str


@dataclass(frozen=True, slots=True)
class InterfaceAccessVlanClaim:
    line: CiscoIosLine
    interface_name: str
    interface_line_number: int
    vlan_id: int


@dataclass(frozen=True, slots=True)
class VlanClaim:
    line: CiscoIosLine
    vlan_id: int


@dataclass(frozen=True, slots=True)
class VlanNameClaim:
    line: CiscoIosLine
    vlan_id: int
    vlan_line_number: int
    vlan_name: str


@dataclass(frozen=True, slots=True)
class InterfaceAdminStateClaim:
    line: CiscoIosLine
    interface_name: str
    interface_line_number: int
    admin_status: str


CiscoIosClaim: TypeAlias = (
    HostnameClaim
    | InterfaceClaim
    | InterfaceDescriptionClaim
    | InterfaceIpv4AddressClaim
    | InterfaceAccessVlanClaim
    | VlanClaim
    | VlanNameClaim
    | InterfaceAdminStateClaim
)


@dataclass(frozen=True, slots=True)
class CiscoIosParseFinding:
    """A safe parse-time finding that retains the exact source line."""

    code: str
    message: str
    line: CiscoIosLine
    field_path: str


@dataclass(frozen=True, slots=True)
class CiscoIosParseResult:
    """Intermediate parse output; proposal construction is intentionally a later step."""

    claims: tuple[CiscoIosClaim, ...]
    findings: tuple[CiscoIosParseFinding, ...]
