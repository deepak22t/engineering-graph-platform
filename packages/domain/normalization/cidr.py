"""CIDR normalization using the standard library parser."""

import ipaddress


def normalize_cidr(value: str) -> str:
    """Return canonical network CIDR; host bits are normalized deterministically."""
    if not isinstance(value, str):
        raise ValueError("CIDR must be a string.")
    try:
        return str(ipaddress.ip_network(value.strip(), strict=False))
    except ValueError as error:
        raise ValueError("CIDR must be a valid IPv4 or IPv6 network.") from error
