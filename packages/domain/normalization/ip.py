"""IP address normalization using the standard library parser."""

import ipaddress


def normalize_ip_address(value: str) -> str:
    """Return a canonical host IP; CIDR input is rejected rather than guessed."""
    if not isinstance(value, str) or "/" in value:
        raise ValueError("IP address must not include a CIDR prefix.")
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError as error:
        raise ValueError("IP address must be a valid IPv4 or IPv6 host address.") from error
