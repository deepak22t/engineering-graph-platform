"""Tests for deterministic shared domain normalization."""
from datetime import datetime, timezone

import pytest

from packages.domain.normalization import (
    normalize_cidr,
    normalize_hostname,
    normalize_interface_name,
    normalize_ip_address,
    normalize_mac_address,
    normalize_text,
    normalize_timestamp,
    normalize_vendor,
    normalize_vlan_id,
    preserve_raw_text,
)


def test_normalizes_valid_canonical_values():
    assert normalize_hostname(" Router-01 ") == "router-01"
    assert normalize_interface_name(" Gi 0/1 ") == "gi 0/1"
    assert normalize_ip_address("2001:0db8::1") == "2001:db8::1"
    assert normalize_cidr("192.168.1.5/24") == "192.168.1.0/24"
    assert normalize_mac_address("00-11-22-33-44-55") == "00:11:22:33:44:55"
    assert normalize_vlan_id(" 010 ") == 10
    assert normalize_vendor(" Cisco Systems ") == "cisco systems"


def test_rejects_invalid_or_ambiguous_inputs_without_guessing():
    with pytest.raises(ValueError):
        normalize_ip_address("192.168.1.5/24")
    with pytest.raises(ValueError):
        normalize_cidr("not-a-network")
    with pytest.raises(ValueError):
        normalize_mac_address("0011.2233.4455.66")
    with pytest.raises(ValueError):
        normalize_vlan_id("ten")
    with pytest.raises(ValueError):
        normalize_text("   ")


def test_preserves_ambiguous_interface_alias_and_raw_text():
    assert normalize_interface_name("GigabitEthernet0/1") == "gigabitethernet0/1"
    raw = preserve_raw_text("  Router-01 ")
    assert raw.raw == "  Router-01 "
    assert raw.value == "router-01"


def test_normalizes_timezone_aware_timestamps_to_utc():
    value = normalize_timestamp("2026-08-07T05:30:00+05:30")
    assert value == datetime(2026, 8, 7, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        normalize_timestamp(datetime(2026, 8, 7))
