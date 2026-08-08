"""Deterministic canonicalization utilities for domain data."""

from packages.domain.normalization.cidr import normalize_cidr
from packages.domain.normalization.hostname import normalize_hostname
from packages.domain.normalization.interface import normalize_interface_name
from packages.domain.normalization.ip import normalize_ip_address
from packages.domain.normalization.mac import normalize_mac_address
from packages.domain.normalization.text import (
    NormalizedValue,
    normalize_text,
    normalize_vendor,
    preserve_raw_text,
)
from packages.domain.normalization.timestamp import normalize_timestamp
from packages.domain.normalization.vlan import normalize_vlan_id

__all__ = [
    "NormalizedValue",
    "normalize_cidr",
    "normalize_hostname",
    "normalize_interface_name",
    "normalize_ip_address",
    "normalize_mac_address",
    "normalize_text",
    "normalize_timestamp",
    "normalize_vendor",
    "normalize_vlan_id",
    "preserve_raw_text",
]
