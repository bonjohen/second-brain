"""Decay functions for belief confidence over time."""

from __future__ import annotations

import math
from datetime import timedelta

DEFAULT_HALF_LIFE_DAYS = 30


def exponential_decay(
    elapsed: timedelta,
    half_life: timedelta = timedelta(days=DEFAULT_HALF_LIFE_DAYS),
) -> float:
    """Compute exponential decay factor for the given elapsed time.

    Returns a value in (0, 1] where 1.0 means no time has passed
    and 0.5 means one half-life has elapsed.
    """
    if half_life.total_seconds() <= 0:
        return 0.0
    seconds = elapsed.total_seconds()
    if seconds <= 0:
        return 1.0
    return math.pow(0.5, seconds / half_life.total_seconds())


def no_decay() -> float:
    """No decay -- always returns 1.0."""
    return 1.0
