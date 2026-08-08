"""Shared conservative text normalization."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedValue:
    """A normalized value paired with its untouched source value when needed."""

    raw: str
    value: str


def normalize_text(value: str, *, casefold: bool = True) -> str:
    """Collapse surrounding/internal whitespace and reject blank text."""
    if not isinstance(value, str):
        raise ValueError("Text value must be a string.")
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError("Text value must not be blank.")
    return normalized.casefold() if casefold else normalized


def normalize_vendor(value: str) -> str:
    """Normalize a vendor label without attempting vendor-name aliases."""
    return normalize_text(value)


def preserve_raw_text(value: str, *, casefold: bool = True) -> NormalizedValue:
    """Return source and canonical text without losing the original representation."""
    return NormalizedValue(raw=value, value=normalize_text(value, casefold=casefold))
