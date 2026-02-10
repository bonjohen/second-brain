"""Confidence computation for beliefs based on supporting/contradicting edges."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from second_brain.core.models import DecayModel, EntityType, RelType
from second_brain.core.rules.decay import exponential_decay, no_decay
from second_brain.core.services.beliefs import BeliefService
from second_brain.core.services.edges import EdgeService
from second_brain.core.utils import parse_utc_datetime


def compute_confidence(
    belief_id: uuid.UUID,
    belief_service: BeliefService,
    edge_service: EdgeService,
    now: datetime | None = None,
) -> float:
    """Compute confidence for a belief based on edge support/contradiction and decay.

    Formula: clamp((supports - contradicts) * decay(time_since_update), 0.0, 1.0)
    """
    belief = belief_service.get_belief(belief_id)
    if belief is None:
        return 0.0

    if now is None:
        now = datetime.now(UTC)

    # Count supports and contradicts edges pointing to this belief
    edges = edge_service.get_edges(
        EntityType.BELIEF, belief_id, direction="incoming"
    )

    supports = sum(1 for e in edges if e.rel_type == RelType.SUPPORTS)
    contradicts = sum(1 for e in edges if e.rel_type == RelType.CONTRADICTS)

    # Parse updated_at if it's a string
    updated_at = parse_utc_datetime(belief.updated_at)

    elapsed = now - updated_at
    if elapsed < timedelta(0):
        elapsed = timedelta(0)

    # Apply decay
    if belief.decay_model == DecayModel.EXPONENTIAL:
        decay_factor = exponential_decay(elapsed)
    else:
        decay_factor = no_decay()

    # Base confidence from edge balance: start at 0.5, add support/contradiction
    # Each support adds 0.1, each contradiction subtracts 0.1
    raw = (0.5 + 0.1 * supports - 0.1 * contradicts) * decay_factor

    # Clamp to [0, 1]
    return max(0.0, min(1.0, raw))
