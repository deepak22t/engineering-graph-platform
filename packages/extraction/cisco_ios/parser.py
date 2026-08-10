"""Deterministic parser for the explicitly supported Cisco IOS running-config subset."""

from __future__ import annotations

import ipaddress
import re

from packages.extraction.cisco_ios.models import (
    CiscoIosClaim,
    CiscoIosLine,
    CiscoIosParseFinding,
    CiscoIosParseResult,
    HostnameClaim,
    InterfaceAccessVlanClaim,
    InterfaceAdminStateClaim,
    InterfaceClaim,
    InterfaceDescriptionClaim,
    InterfaceIpv4AddressClaim,
    VlanClaim,
    VlanNameClaim,
)
from packages.extraction.cisco_ios.scanner import is_block_terminator, scan_cisco_ios_lines

_HOSTNAME_PATTERN = re.compile(r"hostname\s+(?P<hostname>\S+)")
_INTERFACE_PATTERN = re.compile(r"interface\s+(?P<interface_name>\S+)")
_INTERFACE_NAME_PATTERN = re.compile(
    r"(?P<interface_type>[A-Za-z]+(?:-[A-Za-z]+)?)(?P<interface_suffix>\S+)"
)
_DESCRIPTION_PATTERN = re.compile(r"description\s+(?P<description>\S(?:.*\S)?)")
_IP_ADDRESS_PATTERN = re.compile(r"ip\s+address\s+(?P<address>\S+)\s+(?P<netmask>\S+)")
_ACCESS_VLAN_PATTERN = re.compile(r"switchport\s+access\s+vlan\s+(?P<vlan_id>\S+)")
_VLAN_PATTERN = re.compile(r"vlan\s+(?P<vlan_id>\S+)")
_NAME_PATTERN = re.compile(r"name\s+(?P<vlan_name>\S(?:.*\S)?)")


class CiscoIosRunningConfigParser:
    """Parse only the approved Cisco IOS grammar into source-located intermediate claims."""

    def parse(self, text: str) -> CiscoIosParseResult:
        """Parse text deterministically without creating proposals or canonical graph facts."""
        claims: list[CiscoIosClaim] = []
        findings: list[CiscoIosParseFinding] = []
        current_interface: InterfaceClaim | None = None
        current_vlan: VlanClaim | None = None

        for line in scan_cisco_ios_lines(text):
            if is_block_terminator(line):
                current_interface = None
                current_vlan = None
                continue

            if not line.is_indented:
                current_interface = None
                current_vlan = None
                interface_claim = self._parse_interface(line, findings)
                if interface_claim is not None:
                    claims.append(interface_claim)
                    current_interface = interface_claim
                    continue
                vlan_claim = self._parse_vlan(line, findings)
                if vlan_claim is not None:
                    claims.append(vlan_claim)
                    current_vlan = vlan_claim
                    continue
                hostname_claim = self._parse_hostname(line, findings)
                if hostname_claim is not None:
                    claims.append(hostname_claim)
                continue

            if current_interface is not None:
                claims.extend(self._parse_interface_subcommand(line, current_interface, findings))
            elif current_vlan is not None:
                vlan_name_claim = self._parse_vlan_subcommand(line, current_vlan, findings)
                if vlan_name_claim is not None:
                    claims.append(vlan_name_claim)

        return CiscoIosParseResult(claims=tuple(claims), findings=tuple(findings))

    @staticmethod
    def _parse_hostname(
        line: CiscoIosLine, findings: list[CiscoIosParseFinding]
    ) -> HostnameClaim | None:
        if not _has_command(line.content, "hostname"):
            return None
        match = _HOSTNAME_PATTERN.fullmatch(line.content)
        if match is None:
            findings.append(
                _finding("invalid_hostname", "hostname requires one value.", line, "hostname")
            )
            return None
        return HostnameClaim(line=line, hostname=match.group("hostname"))

    @staticmethod
    def _parse_interface(
        line: CiscoIosLine, findings: list[CiscoIosParseFinding]
    ) -> InterfaceClaim | None:
        if not _has_command(line.content, "interface"):
            return None
        match = _INTERFACE_PATTERN.fullmatch(line.content)
        if match is None:
            findings.append(
                _finding(
                    "invalid_interface", "interface requires one complete name.", line, "interface"
                )
            )
            return None
        interface_name = match.group("interface_name")
        name_match = _INTERFACE_NAME_PATTERN.fullmatch(interface_name)
        if name_match is None:
            findings.append(
                _finding(
                    "invalid_interface_name",
                    "interface name requires an alphabetic type prefix and suffix.",
                    line,
                    "interface_name",
                )
            )
            return None
        return InterfaceClaim(
            line=line,
            interface_name=interface_name,
            interface_type=name_match.group("interface_type"),
        )

    @staticmethod
    def _parse_vlan(line: CiscoIosLine, findings: list[CiscoIosParseFinding]) -> VlanClaim | None:
        if not _has_command(line.content, "vlan"):
            return None
        match = _VLAN_PATTERN.fullmatch(line.content)
        if match is None:
            findings.append(
                _finding("invalid_vlan", "vlan requires one numeric ID.", line, "vlan_id")
            )
            return None
        vlan_id = _parse_vlan_id(match.group("vlan_id"), line, findings)
        return VlanClaim(line=line, vlan_id=vlan_id) if vlan_id is not None else None

    @staticmethod
    def _parse_interface_subcommand(
        line: CiscoIosLine,
        interface: InterfaceClaim,
        findings: list[CiscoIosParseFinding],
    ) -> tuple[CiscoIosClaim, ...]:
        if _has_command(line.content, "description"):
            match = _DESCRIPTION_PATTERN.fullmatch(line.content)
            if match is None:
                findings.append(
                    _finding(
                        "invalid_interface_description",
                        "description requires non-blank text.",
                        line,
                        "properties.description",
                    )
                )
                return ()
            return (
                InterfaceDescriptionClaim(
                    line=line,
                    interface_name=interface.interface_name,
                    interface_line_number=interface.line.number,
                    description=match.group("description"),
                ),
            )
        if _has_command(line.content, "ip address"):
            return CiscoIosRunningConfigParser._parse_ipv4_address(line, interface, findings)
        if _has_command(line.content, "switchport access vlan"):
            match = _ACCESS_VLAN_PATTERN.fullmatch(line.content)
            if match is None:
                findings.append(
                    _finding(
                        "invalid_access_vlan",
                        "switchport access vlan requires one numeric ID.",
                        line,
                        "properties.vlan_id",
                    )
                )
                return ()
            vlan_id = _parse_vlan_id(match.group("vlan_id"), line, findings)
            return (
                (
                    InterfaceAccessVlanClaim(
                        line=line,
                        interface_name=interface.interface_name,
                        interface_line_number=interface.line.number,
                        vlan_id=vlan_id,
                    ),
                )
                if vlan_id is not None
                else ()
            )
        if line.content == "shutdown":
            return (
                InterfaceAdminStateClaim(
                    line=line,
                    interface_name=interface.interface_name,
                    interface_line_number=interface.line.number,
                    admin_status="down",
                ),
            )
        if line.content == "no shutdown":
            return (
                InterfaceAdminStateClaim(
                    line=line,
                    interface_name=interface.interface_name,
                    interface_line_number=interface.line.number,
                    admin_status="up",
                ),
            )
        if _has_command(line.content, "shutdown") or _has_command(line.content, "no shutdown"):
            findings.append(
                _finding(
                    "invalid_admin_status",
                    "shutdown and no shutdown do not accept additional values.",
                    line,
                    "properties.admin_status",
                )
            )
        return ()

    @staticmethod
    def _parse_ipv4_address(
        line: CiscoIosLine,
        interface: InterfaceClaim,
        findings: list[CiscoIosParseFinding],
    ) -> tuple[CiscoIosClaim, ...]:
        match = _IP_ADDRESS_PATTERN.fullmatch(line.content)
        if match is None:
            findings.append(
                _finding(
                    "invalid_interface_ipv4_address",
                    "ip address requires one IPv4 address and one IPv4 netmask.",
                    line,
                    "properties.address",
                )
            )
            return ()
        address = match.group("address")
        netmask = match.group("netmask")
        try:
            if ipaddress.ip_address(address).version != 4:
                raise ValueError
            network = ipaddress.ip_network(f"{address}/{netmask}", strict=False)
            if network.version != 4:
                raise ValueError
        except ValueError:
            findings.append(
                _finding(
                    "invalid_interface_ipv4_address",
                    "ip address requires a valid IPv4 address and netmask.",
                    line,
                    "properties.address",
                )
            )
            return ()
        return (
            InterfaceIpv4AddressClaim(
                line=line,
                interface_name=interface.interface_name,
                interface_line_number=interface.line.number,
                address=address,
                netmask=netmask,
                network_cidr=str(network),
            ),
        )

    @staticmethod
    def _parse_vlan_subcommand(
        line: CiscoIosLine,
        vlan: VlanClaim,
        findings: list[CiscoIosParseFinding],
    ) -> VlanNameClaim | None:
        if not _has_command(line.content, "name"):
            return None
        match = _NAME_PATTERN.fullmatch(line.content)
        if match is None:
            findings.append(
                _finding(
                    "invalid_vlan_name",
                    "VLAN name requires non-blank text.",
                    line,
                    "properties.vlan_name",
                )
            )
            return None
        return VlanNameClaim(
            line=line,
            vlan_id=vlan.vlan_id,
            vlan_line_number=vlan.line.number,
            vlan_name=match.group("vlan_name"),
        )


def _has_command(content: str, command: str) -> bool:
    return (
        content == command
        or content.startswith(f"{command} ")
        or content.startswith(f"{command}\t")
    )


def _parse_vlan_id(
    value: str, line: CiscoIosLine, findings: list[CiscoIosParseFinding]
) -> int | None:
    if not value.isdecimal():
        findings.append(
            _finding(
                "invalid_vlan_id", "VLAN ID must contain only decimal digits.", line, "vlan_id"
            )
        )
        return None
    vlan_id = int(value)
    if not 1 <= vlan_id <= 4094:
        findings.append(
            _finding("invalid_vlan_id", "VLAN ID must be between 1 and 4094.", line, "vlan_id")
        )
        return None
    return vlan_id


def _finding(code: str, message: str, line: CiscoIosLine, field_path: str) -> CiscoIosParseFinding:
    return CiscoIosParseFinding(code=code, message=message, line=line, field_path=field_path)
