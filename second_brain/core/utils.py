"""Shared utility helpers for the core layer."""

from __future__ import annotations

from datetime import UTC, datetime


def parse_utc_datetime(value: str | datetime) -> datetime:
    """Parse a datetime value, ensuring it is timezone-aware (UTC).

    Accepts an ISO-format string or a datetime instance.
    Naive datetimes are assumed to be UTC.
    """
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value
