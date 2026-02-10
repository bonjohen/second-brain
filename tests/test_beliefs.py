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
