"""Timestamp normalization."""

from datetime import datetime, timezone


def normalize_timestamp(value: datetime | str) -> datetime:
    """Parse a timezone-aware timestamp and convert it to UTC."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware.")
    return value.astimezone(timezone.utc)
