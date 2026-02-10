"""Tests for automatic belief lifecycle transitions."""

import uuid

from second_brain.core.models import BeliefStatus, EntityType, RelType
from second_brain.core.rules.lifecycle import auto_transition_beliefs


class TestLifecycle:
    def test_proposed_to_active(self, belief_service, edge_service):
        """Proposed belief with sufficient support and no contradictions activates."""
        b = belief_service.create_belief(claim_text="Activatable belief", confidence=0.5)

        # Add supports edges to boost confidence
        for _ in range(3):
            edge_service.create_edge(
                EntityType.NOTE, uuid.uuid4(), RelType.SUPPORTS,
                EntityType.BELIEF, b.belief_id,
            )

        result = auto_transition_beliefs(belief_service, edge_service)
        assert b.belief_id in result["activated"]

        updated = belief_service.get_belief(b.belief_id)
        assert updated.status == BeliefStatus.ACTIVE

    def test_proposed_not_activated_low_confidence(self, belief_service, edge_service):
        """Proposed belief with no support stays proposed."""
        b = belief_service.create_belief(claim_text="Low support belief", confidence=0.1)

        result = auto_transition_beliefs(belief_service, edge_service)
        assert b.belief_id not in result["activated"]

        updated = belief_service.get_belief(b.belief_id)
        assert updated.status == BeliefStatus.PROPOSED

    def test_challenged_to_deprecated(self, belief_service, edge_service):
        """Challenged belief with low confidence gets deprecated."""
        b = belief_service.create_belief(claim_text="Losing belief", confidence=0.5)
        belief_service.update_belief_status(b.belief_id, BeliefStatus.ACTIVE)
        belief_service.update_belief_status(b.belief_id, BeliefStatus.CHALLENGED)

        # Add contradicts edges to lower confidence
        for _ in range(5):
            edge_service.create_edge(
                EntityType.BELIEF, uuid.uuid4(), RelType.CONTRADICTS,
                EntityType.BELIEF, b.belief_id,
            )

        result = auto_transition_beliefs(belief_service, edge_service)
        assert b.belief_id in result["deprecated"]

        updated = belief_service.get_belief(b.belief_id)
        assert updated.status == BeliefStatus.DEPRECATED

    def test_challenged_stays_if_confident(self, belief_service, edge_service):
        """Challenged belief with decent support stays challenged."""
        b = belief_service.create_belief(claim_text="Resilient belief", confidence=0.7)
        belief_service.update_belief_status(b.belief_id, BeliefStatus.ACTIVE)
        belief_service.update_belief_status(b.belief_id, BeliefStatus.CHALLENGED)

        # Add supports to keep confidence up
        for _ in range(5):
            edge_service.create_edge(
                EntityType.NOTE, uuid.uuid4(), RelType.SUPPORTS,
                EntityType.BELIEF, b.belief_id,
            )

        result = auto_transition_beliefs(belief_service, edge_service)
        assert b.belief_id not in result["deprecated"]
