"""ChallengerAgent -- detects contradictions and challenges beliefs."""

from __future__ import annotations

import uuid

from second_brain.core.models import BeliefStatus, EntityType, RelType
from second_brain.core.rules.confidence import compute_confidence
from second_brain.core.rules.contradictions import detect_contradictions
from second_brain.core.services.beliefs import BeliefService
from second_brain.core.services.edges import EdgeService
from second_brain.core.services.signals import SignalService


class ChallengerAgent:
    """Processes belief_proposed and new_note signals to detect contradictions.

    For each proposed belief:
    1. Run contradiction detection.
    2. Create contradicts edges.
    3. Transition conflicting beliefs to challenged.
    4. Recompute confidence.
    5. Emit belief_challenged signal.
    """

    def __init__(
        self,
        belief_service: BeliefService,
        edge_service: EdgeService,
        signal_service: SignalService,
    ) -> None:
        self._beliefs = belief_service
        self._edges = edge_service
        self._signals = signal_service

    def run(self) -> list[uuid.UUID]:
        """Process signals and challenge contradicting beliefs.

        Returns list of belief IDs that were challenged.
        """
        challenged_ids: list[uuid.UUID] = []

        # Process belief_proposed signals
        signals = self._signals.get_unprocessed("belief_proposed")
        for signal in signals:
            bid_str = signal.payload.get("belief_id")
            if bid_str:
                bid = uuid.UUID(bid_str)
                challenged = self._check_contradictions(bid)
                challenged_ids.extend(challenged)
            self._signals.mark_processed(signal.signal_id)

        return challenged_ids

    def _check_contradictions(self, belief_id: uuid.UUID) -> list[uuid.UUID]:
        """Check a belief for contradictions and challenge any found."""
        contradicting_ids = detect_contradictions(
            belief_id, self._beliefs, self._edges
        )

        challenged: list[uuid.UUID] = []
        for other_id in contradicting_ids:
            other = self._beliefs.get_belief(other_id)
            if other is None:
                continue

            # Create contradicts edge
            self._edges.create_edge(
                from_type=EntityType.BELIEF,
                from_id=belief_id,
                rel_type=RelType.CONTRADICTS,
                to_type=EntityType.BELIEF,
                to_id=other_id,
            )

            # Transition to challenged if currently active
            if other.status == BeliefStatus.ACTIVE:
                self._beliefs.update_belief_status(other_id, BeliefStatus.CHALLENGED)
                challenged.append(other_id)

            # Recompute confidence for the contradicted belief
            new_conf = compute_confidence(other_id, self._beliefs, self._edges)
            self._beliefs.update_confidence(other_id, new_conf)

            self._signals.emit(
                "belief_challenged",
                {
                    "belief_id": str(other_id),
                    "challenged_by": str(belief_id),
                },
            )

        return challenged
