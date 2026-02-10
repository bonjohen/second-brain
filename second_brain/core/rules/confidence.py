"""Confidence computation for beliefs based on supporting/contradicting edges."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from second_brain.core.models import DecayModel, EntityType, RelType
from second_brain.core.rules.decay import exponential_decay, no_decay
from second_brain.core.services.beliefs import BeliefService
from second_brain.core.services.edges import EdgeService
from second_brain.core.utils import parse_utc_datetime

DEFAULT_BASE_CONFIDENCE = 0.5
DEFAULT_SUPPORT_WEIGHT = 0.1
DEFAULT_CONTRADICTION_WEIGHT = 0.1


def compute_confidence(
    belief_id: uuid.UUID,
    belief_service: BeliefService,
    edge_service: EdgeService,
    now: datetime | None = None,
    base_confidence: float = DEFAULT_BASE_CONFIDENCE,
    support_weight: float = DEFAULT_SUPPORT_WEIGHT,
    contradiction_weight: float = DEFAULT_CONTRADICTION_WEIGHT,
) -> float:
    """Compute confidence for a belief based on edge support/contradiction and decay.

    Formula: clamp((base + support_weight*supports - contradiction_weight*contradicts)
                    * decay(time_since_update), 0.0, 1.0)
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

    # Base confidence from edge balance
    edge_score = base_confidence + support_weight * supports - contradiction_weight * contradicts
    raw = edge_score * decay_factor

    # Clamp to [0, 1]
    return max(0.0, min(1.0, raw))
