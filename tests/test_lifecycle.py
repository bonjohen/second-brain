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

    def test_paginates_proposed_beliefs(self, belief_service, edge_service):
        """auto_transition should paginate and not miss beliefs beyond one batch."""
        # Track calls to list_beliefs
        original_list = belief_service.list_beliefs
        calls: list[dict] = []

        def tracking_list(*args, **kwargs):
            calls.append(kwargs.copy())
            return original_list(*args, **kwargs)

        belief_service.list_beliefs = tracking_list

        # Create 3 proposed beliefs
        for i in range(3):
            belief_service.create_belief(claim_text=f"Paginated belief {i}")

        auto_transition_beliefs(belief_service, edge_service)

        # Pagination should have made at least 2 calls for proposed
        # (one returning results, one returning empty)
        proposed_calls = [
            c for c in calls
            if c.get("status_filter") == "proposed"
        ]
        assert len(proposed_calls) >= 2

        belief_service.list_beliefs = original_list
