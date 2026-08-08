"""MAC address normalization."""

import re


def normalize_mac_address(value: str) -> str:
    """Return lowercase colon-separated EUI-48, rejecting ambiguous formats."""
    if not isinstance(value, str):
        raise ValueError("MAC address must be a string.")
    compact = re.sub(r"[-:.\s]", "", value)
    if not re.fullmatch(r"[0-9A-Fa-f]{12}", compact):
        raise ValueError("MAC address must contain exactly 12 hexadecimal digits.")
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2)).lower()
