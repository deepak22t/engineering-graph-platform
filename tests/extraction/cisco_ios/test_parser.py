"""Tests for the line-aware Cisco IOS running-config parser."""

from pathlib import Path

from packages.extraction.cisco_ios import (
    CiscoIosRunningConfigParser,
    HostnameClaim,
    InterfaceAccessVlanClaim,
    InterfaceAdminStateClaim,
    InterfaceClaim,
    InterfaceDescriptionClaim,
    InterfaceIpv4AddressClaim,
    VlanClaim,
    VlanNameClaim,
    scan_cisco_ios_lines,
)

FIXTURE_PATH = (
    Path(__file__).parents[2] / "fixtures" / "artifacts" / "edge-router-01-running-config.cfg"
)


def parse(text: str):
    return CiscoIosRunningConfigParser().parse(text)


def test_scanner_preserves_original_line_numbers_and_raw_text():
    lines = tuple(scan_cisco_ios_lines("hostname router-01\n!\n interface Gi0/1  \n"))

    assert [(line.number, line.raw, line.is_indented) for line in lines] == [
        (1, "hostname router-01", False),
        (2, "!", False),
        (3, " interface Gi0/1  ", True),
    ]


def test_parser_extracts_the_documented_sanitized_config_fixture():
    result = parse(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert result.findings == ()
    assert isinstance(result.claims[0], HostnameClaim)
    assert isinstance(result.claims[1], InterfaceClaim)
    assert isinstance(result.claims[2], InterfaceDescriptionClaim)
    assert isinstance(result.claims[3], InterfaceIpv4AddressClaim)
    assert isinstance(result.claims[4], InterfaceAdminStateClaim)
    assert result.claims[0].hostname == "edge-router-01"
    assert result.claims[1].interface_name == "GigabitEthernet0/1"
    assert result.claims[1].interface_type == "GigabitEthernet"
    assert result.claims[2].description == "Uplink to distribution switch"
    assert result.claims[2].interface_line_number == 4
    assert result.claims[3].network_cidr == "192.0.2.0/30"
    assert result.claims[3].interface_line_number == 4
    assert result.claims[4].admin_status == "up"
    assert result.claims[4].interface_line_number == 4
    assert [claim.line.number for claim in result.claims] == [2, 4, 5, 6, 7]


def test_parser_tracks_interface_and_vlan_submodes_without_guessing():
    result = parse(
        """hostname switch-01
interface GigabitEthernet1/0/1
 switchport access vlan 10
 shutdown
!
vlan 10
 name Users
"""
    )

    assert isinstance(result.claims[1], InterfaceClaim)
    assert isinstance(result.claims[2], InterfaceAccessVlanClaim)
    assert isinstance(result.claims[3], InterfaceAdminStateClaim)
    assert isinstance(result.claims[4], VlanClaim)
    assert isinstance(result.claims[5], VlanNameClaim)
    assert result.claims[2].interface_name == "GigabitEthernet1/0/1"
    assert result.claims[2].vlan_id == 10
    assert result.claims[3].admin_status == "down"
    assert result.claims[5].vlan_name == "Users"


def test_unknown_commands_and_out_of_context_subcommands_create_no_claims():
    result = parse(
        """hostname router-01
router ospf 1
 network 10.0.0.0 0.0.0.255 area 0
 description not-an-interface-description
"""
    )

    assert len(result.claims) == 1
    assert isinstance(result.claims[0], HostnameClaim)
    assert result.findings == ()


def test_invalid_supported_syntax_becomes_line_aware_findings_without_claims():
    result = parse(
        """hostname
interface 123
 description orphaned
interface GigabitEthernet0/1
 ip address 192.0.2.1 not-a-mask
 switchport access vlan 4095
 shutdown later
vlan ten
"""
    )

    assert result.claims == (
        InterfaceClaim(
            line=result.claims[0].line,
            interface_name="GigabitEthernet0/1",
            interface_type="GigabitEthernet",
        ),
    )
    assert [(finding.code, finding.line.number) for finding in result.findings] == [
        ("invalid_hostname", 1),
        ("invalid_interface_name", 2),
        ("invalid_interface_ipv4_address", 5),
        ("invalid_vlan_id", 6),
        ("invalid_admin_status", 7),
        ("invalid_vlan_id", 8),
    ]


def test_parser_rejects_ipv6_secondary_and_extra_tokens_without_creating_ip_claims():
    result = parse(
        """interface GigabitEthernet0/1
 ip address 2001:db8::1 ffff:ffff:ffff:ffff::
 ip address 192.0.2.1 255.255.255.0 secondary
"""
    )

    assert result.claims == (
        InterfaceClaim(
            line=result.claims[0].line,
            interface_name="GigabitEthernet0/1",
            interface_type="GigabitEthernet",
        ),
    )
    assert [(finding.code, finding.line.number) for finding in result.findings] == [
        ("invalid_interface_ipv4_address", 2),
        ("invalid_interface_ipv4_address", 3),
    ]
