"""Hostname normalization."""

from packages.domain.normalization.text import normalize_text


def normalize_hostname(value: str) -> str:
    """Normalize hostnames conservatively; no DNS lookup or alias expansion occurs."""
    return normalize_text(value)
