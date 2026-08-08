"""Interface-name normalization."""

from packages.domain.normalization.text import normalize_text


def normalize_interface_name(value: str) -> str:
    """Normalize spacing and case without guessing vendor-specific aliases."""
    return normalize_text(value)
