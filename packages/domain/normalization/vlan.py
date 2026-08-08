"""VLAN identifier normalization."""


def normalize_vlan_id(value: int | str) -> int:
    """Parse a decimal VLAN ID in the IEEE 802.1Q usable range."""
    if isinstance(value, bool):
        raise ValueError("VLAN ID must be an integer.")
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped.isdecimal():
            raise ValueError("VLAN ID must be a decimal integer.")
        value = int(stripped, 10)
    if not isinstance(value, int) or not 1 <= value <= 4094:
        raise ValueError("VLAN ID must be between 1 and 4094.")
    return value
