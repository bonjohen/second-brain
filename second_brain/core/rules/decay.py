"""Decay rules — exponential time-based decay for belief confidence.

Per design.md Section 6.1: decay(time_since_last_update)
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

# Half-life in days — confidence halves every HALF_LIFE_DAYS if not updated
HALF_LIFE_DAYS = 30.0


def compute_decay(
    updated_at_iso: str,
    decay_model: str = "exponential",
    half_life_days: float = HALF_LIFE_DAYS,
    now: datetime | None = None,
) -> float:
    """Compute decay factor [0.0, 1.0] based on time since last update.

    Returns 1.0 for decay_model="none".
    """
    if decay_model == "none":
        return 1.0

    if now is None:
        now = datetime.now(timezone.utc)

    # Parse the timestamp
    if isinstance(updated_at_iso, str):
        updated_at = datetime.fromisoformat(updated_at_iso)
    else:
        updated_at = updated_at_iso

    # Ensure timezone-aware
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    days_elapsed = (now - updated_at).total_seconds() / 86400.0
    if days_elapsed <= 0:
        return 1.0

    # Exponential decay: factor = 2^(-t/half_life)
    return math.pow(2, -days_elapsed / half_life_days)
