"""Tests for BeliefService."""

import uuid

import pytest

from second_brain.core.models import BeliefStatus, DecayModel


class TestBeliefService:
    def test_create_belief(self, belief_service):
        belief = belief_service.create_belief(
            claim_text="Python is versatile",
            confidence=0.7,
            derived_from_agent="synthesis",
        )
        assert belief.claim_text == "Python is versatile"
        assert belief.confidence == 0.7
        assert belief.status == BeliefStatus.PROPOSED
        assert belief.derived_from_agent == "synthesis"

    def test_create_belief_defaults(self, belief_service):
        belief = belief_service.create_belief(claim_text="Test claim")
        assert belief.confidence == 0.5
        assert belief.decay_model == DecayModel.EXPONENTIAL
        assert belief.scope == {}

    def test_get_belief(self, belief_service):
        created = belief_service.create_belief(claim_text="Findable claim")
        retrieved = belief_service.get_belief(created.belief_id)
        assert retrieved is not None
        assert retrieved.claim_text == "Findable claim"

    def test_get_belief_not_found(self, belief_service):
        result = belief_service.get_belief(uuid.uuid4())
        assert result is None

    def test_list_beliefs(self, belief_service):
        belief_service.create_belief(claim_text="Belief 1")
        belief_service.create_belief(claim_text="Belief 2")
        beliefs = belief_service.list_beliefs()
        assert len(beliefs) == 2

    def test_list_beliefs_with_status_filter(self, belief_service):
        belief_service.create_belief(claim_text="Proposed belief")
        beliefs = belief_service.list_beliefs(status_filter=BeliefStatus.PROPOSED)
        assert len(beliefs) == 1
        assert beliefs[0].status == BeliefStatus.PROPOSED

        active = belief_service.list_beliefs(status_filter=BeliefStatus.ACTIVE)
        assert len(active) == 0

    def test_update_status_proposed_to_active(self, belief_service):
        belief = belief_service.create_belief(claim_text="Will be activated")
        updated = belief_service.update_belief_status(belief.belief_id, BeliefStatus.ACTIVE)
        assert updated.status == BeliefStatus.ACTIVE

    def test_update_status_active_to_challenged(self, belief_service):
        belief = belief_service.create_belief(claim_text="Will be challenged")
        belief_service.update_belief_status(belief.belief_id, BeliefStatus.ACTIVE)
        updated = belief_service.update_belief_status(belief.belief_id, BeliefStatus.CHALLENGED)
        assert updated.status == BeliefStatus.CHALLENGED

    def test_update_status_invalid_transition(self, belief_service):
        belief = belief_service.create_belief(claim_text="Cannot skip")
        with pytest.raises(ValueError, match="Invalid transition"):
            belief_service.update_belief_status(belief.belief_id, BeliefStatus.DEPRECATED)

    def test_update_status_not_found(self, belief_service):
        with pytest.raises(ValueError, match="Belief not found"):
            belief_service.update_belief_status(uuid.uuid4(), BeliefStatus.ACTIVE)

    def test_update_confidence(self, belief_service):
        belief = belief_service.create_belief(claim_text="Confidence test", confidence=0.5)
        updated = belief_service.update_confidence(belief.belief_id, 0.8)
        assert updated.confidence == 0.8

    def test_update_confidence_clamped_high(self, belief_service):
        belief = belief_service.create_belief(claim_text="Clamp test")
        updated = belief_service.update_confidence(belief.belief_id, 1.5)
        assert updated.confidence == 1.0

    def test_update_confidence_clamped_low(self, belief_service):
        belief = belief_service.create_belief(claim_text="Clamp test low")
        updated = belief_service.update_confidence(belief.belief_id, -0.5)
        assert updated.confidence == 0.0

    def test_update_confidence_not_found(self, belief_service):
        with pytest.raises(ValueError, match="Belief not found"):
            belief_service.update_confidence(uuid.uuid4(), 0.5)

    def test_belief_audit_logged(self, belief_service, audit_service):
        belief = belief_service.create_belief(claim_text="Audited belief")
        history = audit_service.get_history("belief", belief.belief_id)
        assert len(history) == 1
        assert history[0].action == "created"

    def test_status_change_audit_logged(self, belief_service, audit_service):
        belief = belief_service.create_belief(claim_text="Status audit test")
        belief_service.update_belief_status(belief.belief_id, BeliefStatus.ACTIVE)
        history = audit_service.get_history("belief", belief.belief_id)
        assert len(history) == 2
        assert history[1].action == "status_changed"
        assert history[1].before is not None
        assert history[1].after is not None

    def test_list_beliefs_pagination(self, belief_service):
        for i in range(5):
            belief_service.create_belief(claim_text=f"Belief {i}")
        page1 = belief_service.list_beliefs(limit=2, offset=0)
        page2 = belief_service.list_beliefs(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0].belief_id != page2[0].belief_id

    # --- Negative / edge-case tests for status transitions ---

    def test_invalid_transition_proposed_to_challenged(self, belief_service):
        belief = belief_service.create_belief(claim_text="Skip active")
        with pytest.raises(ValueError, match="Invalid transition"):
            belief_service.update_belief_status(belief.belief_id, BeliefStatus.CHALLENGED)

    def test_invalid_transition_proposed_to_archived(self, belief_service):
        belief = belief_service.create_belief(claim_text="Skip to archived")
        with pytest.raises(ValueError, match="Invalid transition"):
            belief_service.update_belief_status(belief.belief_id, BeliefStatus.ARCHIVED)

    def test_invalid_transition_active_to_deprecated(self, belief_service):
        belief = belief_service.create_belief(claim_text="Skip challenged")
        belief_service.update_belief_status(belief.belief_id, BeliefStatus.ACTIVE)
        with pytest.raises(ValueError, match="Invalid transition"):
            belief_service.update_belief_status(belief.belief_id, BeliefStatus.DEPRECATED)

    def test_invalid_transition_archived_to_anything(self, belief_service):
        """Archived is a terminal state -- no transitions allowed."""
        belief = belief_service.create_belief(claim_text="Terminal state")
        belief_service.update_belief_status(belief.belief_id, BeliefStatus.ACTIVE)
        belief_service.update_belief_status(belief.belief_id, BeliefStatus.CHALLENGED)
        belief_service.update_belief_status(belief.belief_id, BeliefStatus.DEPRECATED)
        belief_service.update_belief_status(belief.belief_id, BeliefStatus.ARCHIVED)
        with pytest.raises(ValueError, match="Invalid transition"):
            belief_service.update_belief_status(belief.belief_id, BeliefStatus.ACTIVE)

    def test_valid_full_lifecycle(self, belief_service):
        """Walk through the complete belief lifecycle."""
        belief = belief_service.create_belief(claim_text="Full lifecycle")
        assert belief.status == BeliefStatus.PROPOSED

        belief = belief_service.update_belief_status(belief.belief_id, BeliefStatus.ACTIVE)
        assert belief.status == BeliefStatus.ACTIVE

        belief = belief_service.update_belief_status(belief.belief_id, BeliefStatus.CHALLENGED)
        assert belief.status == BeliefStatus.CHALLENGED

        belief = belief_service.update_belief_status(belief.belief_id, BeliefStatus.DEPRECATED)
        assert belief.status == BeliefStatus.DEPRECATED

        belief = belief_service.update_belief_status(belief.belief_id, BeliefStatus.ARCHIVED)
        assert belief.status == BeliefStatus.ARCHIVED

    def test_challenged_can_return_to_active(self, belief_service):
        """Challenged beliefs can be re-confirmed back to active."""
        belief = belief_service.create_belief(claim_text="Recoverable")
        belief_service.update_belief_status(belief.belief_id, BeliefStatus.ACTIVE)
        belief_service.update_belief_status(belief.belief_id, BeliefStatus.CHALLENGED)
        updated = belief_service.update_belief_status(belief.belief_id, BeliefStatus.ACTIVE)
        assert updated.status == BeliefStatus.ACTIVE
