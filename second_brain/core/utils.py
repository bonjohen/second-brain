"""Shared utility helpers for the core layer."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


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


def safe_json_loads(raw: str | None, default=None, context: str = ""):
    """Parse JSON with graceful fallback on decode errors.

    Returns *default* when *raw* is None or contains malformed JSON,
    logging a warning so corrupted rows are visible without crashing
    the entire query.
    """
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Corrupt JSON in %s: %r", context or "unknown field", raw[:120])
        return default
