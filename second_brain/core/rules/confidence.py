"""Confidence calculation — deterministic formula per design.md Section 6.1.

confidence = clamp(
    (Σ support_weights - Σ counter_weights) * decay(time_since_last_update),
    0.0,
    1.0
)
"""

from __future__ import annotations

from second_brain.core.rules.decay import compute_decay
from second_brain.core.services.edges import EdgeService
from second_brain.storage.sqlite import Database

# Default weight for each supporting/contradicting edge
DEFAULT_SUPPORT_WEIGHT = 0.3
DEFAULT_COUNTER_WEIGHT = 0.3

# Threshold for activating a proposed belief
ACTIVATION_THRESHOLD = 0.6


def compute_confidence(
    db: Database,
    belief_id: str,
    updated_at_iso: str,
    decay_model: str = "exponential",
    support_weight: float = DEFAULT_SUPPORT_WEIGHT,
    counter_weight: float = DEFAULT_COUNTER_WEIGHT,
) -> float:
    """Compute belief confidence from edges and time decay."""
    edge_svc = EdgeService(db)

    supports = edge_svc.get_support_edges(belief_id)
    contradictions = edge_svc.get_contradiction_edges(belief_id)

    total_support = len(supports) * support_weight
    total_counter = len(contradictions) * counter_weight

    raw = total_support - total_counter
    decay_factor = compute_decay(updated_at_iso, decay_model)

    return max(0.0, min(1.0, raw * decay_factor))
