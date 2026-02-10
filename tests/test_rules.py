"""Tests for rules: decay, confidence, contradictions."""

import uuid
from datetime import timedelta

from second_brain.core.models import BeliefStatus, EntityType, RelType
from second_brain.core.rules.confidence import compute_confidence
from second_brain.core.rules.contradictions import (
    _has_opposing_words,
    _is_negation,
    detect_contradictions,
    load_candidate_beliefs,
)
from second_brain.core.rules.decay import exponential_decay, no_decay


class TestDecay:
    def test_no_decay_returns_one(self):
        assert no_decay() == 1.0

    def test_exponential_decay_zero_elapsed(self):
        result = exponential_decay(timedelta(0))
        assert result == 1.0

    def test_exponential_decay_one_half_life(self):
        result = exponential_decay(timedelta(days=30), half_life=timedelta(days=30))
        assert abs(result - 0.5) < 1e-10

    def test_exponential_decay_two_half_lives(self):
        result = exponential_decay(timedelta(days=60), half_life=timedelta(days=30))
        assert abs(result - 0.25) < 1e-10

    def test_exponential_decay_negative_elapsed(self):
        result = exponential_decay(timedelta(days=-1))
        assert result == 1.0

    def test_exponential_decay_zero_half_life(self):
        result = exponential_decay(timedelta(days=1), half_life=timedelta(0))
        assert result == 0.0


class TestConfidence:
    def test_confidence_no_edges(self, belief_service, edge_service):
        belief = belief_service.create_belief(claim_text="No edges test")
        conf = compute_confidence(belief.belief_id, belief_service, edge_service)
        # Base: 0.5, no edges, minimal decay
        assert 0.0 <= conf <= 1.0
        assert conf > 0.0

    def test_confidence_with_supports(self, belief_service, edge_service):
        belief = belief_service.create_belief(claim_text="Supported belief")
        # Add supports edges
        for _ in range(3):
            edge_service.create_edge(
                EntityType.NOTE, uuid.uuid4(), RelType.SUPPORTS, EntityType.BELIEF, belief.belief_id
            )
        conf = compute_confidence(belief.belief_id, belief_service, edge_service)
        assert conf > 0.5  # More supports = higher confidence

    def test_confidence_with_contradicts(self, belief_service, edge_service):
        belief = belief_service.create_belief(claim_text="Contradicted belief")
        for _ in range(5):
            edge_service.create_edge(
                EntityType.NOTE, uuid.uuid4(), RelType.CONTRADICTS,
                EntityType.BELIEF, belief.belief_id,
            )
        conf = compute_confidence(belief.belief_id, belief_service, edge_service)
        assert conf == 0.0  # Many contradictions = clamped to 0

    def test_confidence_nonexistent_belief(self, belief_service, edge_service):
        conf = compute_confidence(uuid.uuid4(), belief_service, edge_service)
        assert conf == 0.0

    def test_confidence_clamped_to_one(self, belief_service, edge_service):
        belief = belief_service.create_belief(claim_text="Heavily supported")
        for _ in range(20):
            edge_service.create_edge(
                EntityType.NOTE, uuid.uuid4(), RelType.SUPPORTS, EntityType.BELIEF, belief.belief_id
            )
        conf = compute_confidence(belief.belief_id, belief_service, edge_service)
        assert conf <= 1.0

    def test_confidence_custom_weights(self, belief_service, edge_service):
        belief = belief_service.create_belief(claim_text="Custom weights test")
        edge_service.create_edge(
            EntityType.NOTE, uuid.uuid4(), RelType.SUPPORTS, EntityType.BELIEF, belief.belief_id
        )
        # With higher support weight, one edge should boost confidence more
        conf_default = compute_confidence(belief.belief_id, belief_service, edge_service)
        conf_custom = compute_confidence(
            belief.belief_id, belief_service, edge_service, support_weight=0.3
        )
        assert conf_custom > conf_default

    def test_confidence_zero_weights(self, belief_service, edge_service):
        """With both weights set to 0, edges should not affect confidence."""
        belief = belief_service.create_belief(claim_text="Zero weights")
        for _ in range(5):
            edge_service.create_edge(
                EntityType.NOTE, uuid.uuid4(), RelType.SUPPORTS,
                EntityType.BELIEF, belief.belief_id,
            )
        conf = compute_confidence(
            belief.belief_id, belief_service, edge_service,
            support_weight=0.0, contradiction_weight=0.0,
        )
        # Should be close to base_confidence * decay (near 0.5)
        assert 0.4 <= conf <= 0.5

    def test_confidence_equal_supports_and_contradicts(self, belief_service, edge_service):
        """Equal supports and contradicts should cancel out, leaving base confidence."""
        belief = belief_service.create_belief(claim_text="Balanced edges")
        for _ in range(3):
            edge_service.create_edge(
                EntityType.NOTE, uuid.uuid4(), RelType.SUPPORTS,
                EntityType.BELIEF, belief.belief_id,
            )
            edge_service.create_edge(
                EntityType.NOTE, uuid.uuid4(), RelType.CONTRADICTS,
                EntityType.BELIEF, belief.belief_id,
            )
        conf = compute_confidence(belief.belief_id, belief_service, edge_service)
        # 0.5 + 0.1*3 - 0.1*3 = 0.5 (times decay)
        assert 0.4 <= conf <= 0.5

    def test_confidence_high_base_with_zero_contradictions(self, belief_service, edge_service):
        """High base confidence with no contradictions stays near base."""
        belief = belief_service.create_belief(claim_text="High base")
        conf = compute_confidence(
            belief.belief_id, belief_service, edge_service,
            base_confidence=0.9,
        )
        assert conf > 0.8


class TestContradictions:
    def test_is_negation_not_insertion(self):
        assert _is_negation("python is fast", "python is not fast")

    def test_is_negation_reverse(self):
        assert _is_negation("python is not fast", "python is fast")

    def test_is_negation_no_match(self):
        assert not _is_negation("python is fast", "rust is fast")

    def test_has_opposing_words(self):
        assert _has_opposing_words({"python", "is", "fast"}, {"python", "is", "slow"})

    def test_has_opposing_words_no_match(self):
        assert not _has_opposing_words({"python", "is", "great"}, {"rust", "is", "great"})

    def test_detect_contradictions_negation(self, belief_service, edge_service):
        b1 = belief_service.create_belief(claim_text="python is fast")
        belief_service.update_belief_status(b1.belief_id, BeliefStatus.ACTIVE)
        b2 = belief_service.create_belief(claim_text="python is not fast")

        contradictions = detect_contradictions(b2.belief_id, belief_service, edge_service)
        assert b1.belief_id in contradictions

    def test_detect_contradictions_opposing_words(self, belief_service, edge_service):
        b1 = belief_service.create_belief(claim_text="python is fast and efficient")
        belief_service.update_belief_status(b1.belief_id, BeliefStatus.ACTIVE)
        b2 = belief_service.create_belief(claim_text="python is slow and efficient")

        contradictions = detect_contradictions(b2.belief_id, belief_service, edge_service)
        assert b1.belief_id in contradictions

    def test_detect_contradictions_no_match(self, belief_service, edge_service):
        b1 = belief_service.create_belief(claim_text="python is great")
        belief_service.update_belief_status(b1.belief_id, BeliefStatus.ACTIVE)
        b2 = belief_service.create_belief(claim_text="rust is great")

        contradictions = detect_contradictions(b2.belief_id, belief_service, edge_service)
        assert b1.belief_id not in contradictions

    def test_detect_contradictions_nonexistent(self, belief_service, edge_service):
        result = detect_contradictions(uuid.uuid4(), belief_service, edge_service)
        assert result == []

    def test_detect_contradictions_with_preloaded_candidates(
        self, belief_service, edge_service
    ):
        """Pre-loaded candidates avoid redundant DB fetches."""
        b1 = belief_service.create_belief(claim_text="python is fast")
        belief_service.update_belief_status(b1.belief_id, BeliefStatus.ACTIVE)
        b2 = belief_service.create_belief(claim_text="python is not fast")

        candidates = load_candidate_beliefs(belief_service)
        contradictions = detect_contradictions(
            b2.belief_id, belief_service, edge_service, candidates=candidates
        )
        assert b1.belief_id in contradictions

    def test_load_candidate_beliefs_caps_at_max(self, belief_service):
        """load_candidate_beliefs respects max_candidates."""
        for i in range(10):
            belief_service.create_belief(claim_text=f"belief {i}")

        capped = load_candidate_beliefs(belief_service, max_candidates=5)
        assert len(capped) == 5

    def test_detect_contradictions_max_candidates(
        self, belief_service, edge_service
    ):
        """With max_candidates=1, only one candidate is checked."""
        b1 = belief_service.create_belief(claim_text="python is fast")
        belief_service.update_belief_status(b1.belief_id, BeliefStatus.ACTIVE)
        b2 = belief_service.create_belief(claim_text="rust is not slow")
        belief_service.update_belief_status(b2.belief_id, BeliefStatus.ACTIVE)
        b3 = belief_service.create_belief(claim_text="python is not fast")

        # With max_candidates=1, only one candidate is loaded — may miss some
        result = detect_contradictions(
            b3.belief_id, belief_service, edge_service, max_candidates=1
        )
        assert len(result) <= 1
