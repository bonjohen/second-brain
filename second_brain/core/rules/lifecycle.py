"""Automatic belief status transitions based on confidence and contradictions."""

from __future__ import annotations

import uuid

from second_brain.core.constants import DEFAULT_BATCH_SIZE
from second_brain.core.models import BeliefStatus
from second_brain.core.rules.confidence import compute_confidence
from second_brain.core.rules.contradictions import (
    detect_contradictions,
    load_candidate_beliefs,
)
from second_brain.core.services.beliefs import BeliefService
from second_brain.core.services.edges import EdgeService

DEFAULT_ACTIVATION_THRESHOLD = 0.6
DEFAULT_DEPRECATION_THRESHOLD = 0.2


def auto_transition_beliefs(
    belief_service: BeliefService,
    edge_service: EdgeService,
    activation_threshold: float = DEFAULT_ACTIVATION_THRESHOLD,
    deprecation_threshold: float = DEFAULT_DEPRECATION_THRESHOLD,
) -> dict[str, list[uuid.UUID]]:
    """Run automatic status transitions on all eligible beliefs.

    Returns dict with keys 'activated', 'deprecated' mapping to lists of belief IDs.
    """
    activated: list[uuid.UUID] = []
    deprecated: list[uuid.UUID] = []

    # Pre-load candidates once for all contradiction checks (avoids O(n²) re-fetch)
    contradiction_candidates = load_candidate_beliefs(belief_service)

    # proposed -> active: confidence >= threshold AND no contradictions
    offset = 0
    batch_size = DEFAULT_BATCH_SIZE
    while True:
        proposed = belief_service.list_beliefs(
            status_filter=BeliefStatus.PROPOSED, limit=batch_size, offset=offset
        )
        if not proposed:
            break
        for belief in proposed:
            conf = compute_confidence(belief.belief_id, belief_service, edge_service)
            contradictions = detect_contradictions(
                belief.belief_id, belief_service, edge_service,
                candidates=contradiction_candidates,
            )
            if conf >= activation_threshold and not contradictions:
                belief_service.update_belief_status(
                    belief.belief_id, BeliefStatus.ACTIVE
                )
                belief_service.update_confidence(belief.belief_id, conf)
                activated.append(belief.belief_id)
        offset += batch_size

    # challenged -> deprecated: confidence below threshold (counterevidence dominates)
    offset = 0
    while True:
        challenged = belief_service.list_beliefs(
            status_filter=BeliefStatus.CHALLENGED, limit=batch_size, offset=offset
        )
        if not challenged:
            break
        for belief in challenged:
            conf = compute_confidence(belief.belief_id, belief_service, edge_service)
            if conf < deprecation_threshold:
                belief_service.update_belief_status(
                    belief.belief_id, BeliefStatus.DEPRECATED
                )
                belief_service.update_confidence(belief.belief_id, conf)
                deprecated.append(belief.belief_id)
        offset += batch_size

    return {"activated": activated, "deprecated": deprecated}
