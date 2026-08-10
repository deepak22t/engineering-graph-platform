"""Tests for typed entity property validation."""

import pytest
from pydantic import ValidationError

from packages.domain.entities import (
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


def test_each_entity_type_has_typed_properties():
    properties = (
        DeviceProperties(hostname="router-01"),
        ComponentProperties(component_type="module"),
        InterfaceProperties(interface_name="Eth0", interface_type="ethernet"),
        NetworkProperties(
            cidr="10.0.0.1/24", address_family=AddressFamily.IPV4, network_type="lan"
        ),
        SiteProperties(site_type="datacenter"),
        ServiceProperties(service_name="api", service_type="application"),
        ContainerProperties(workload_name="api", image="repo/api:1", runtime="kubernetes"),
        IPAddressProperties(address="10.0.0.1", address_family=AddressFamily.IPV4),
        VlanProperties(vlan_id=100, vlan_name="Users"),
        RouteProperties(destination_cidr="10.1.0.9/16", next_hop="10.0.0.1", protocol="static"),
        FirewallProperties(firewall_type="appliance"),
        ConnectionProperties(connection_type="fiber", operational_status=LinkStatus.UP),
    )
    assert len(properties) == 12


def test_engineering_values_are_normalized_and_invalid_values_rejected():
    interface = InterfaceProperties(
        interface_name=" Eth0 ",
        interface_type=" Ethernet ",
        description=" Uplink to distribution switch ",
        mac_address="AA-BB-CC-DD-EE-FF",
    )
    assert interface.interface_name == "eth0"
    assert interface.description == "Uplink to distribution switch"
    assert interface.mac_address == "aa:bb:cc:dd:ee:ff"
    with pytest.raises(ValidationError):
        InterfaceProperties(interface_name="eth0", interface_type="ethernet", mac_address="bad")
    with pytest.raises(ValidationError):
        VlanProperties(vlan_id=4095)
    with pytest.raises(ValidationError):
        NetworkProperties(cidr="bad", address_family=AddressFamily.IPV4, network_type="lan")
    with pytest.raises(ValidationError):
        IPAddressProperties(address="10.0.0.1", address_family=AddressFamily.IPV6)
    with pytest.raises(ValidationError):
        RouteProperties(destination_cidr="10.0.0.0/24", next_hop="not-ip", protocol="static")
