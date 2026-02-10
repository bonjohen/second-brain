"""Tests for ChallengerAgent."""

from second_brain.agents.challenger import ChallengerAgent
from second_brain.core.models import BeliefStatus, EntityType, RelType


class TestChallengerAgent:
    def _make_agent(self, belief_service, edge_service, signal_service):
        return ChallengerAgent(belief_service, edge_service, signal_service)

    def test_run_no_signals(self, belief_service, edge_service, signal_service):
        agent = self._make_agent(belief_service, edge_service, signal_service)
        result = agent.run()
        assert result == []

    def test_run_no_contradictions(self, belief_service, edge_service, signal_service):
        """Non-contradicting beliefs should not be challenged."""
        agent = self._make_agent(belief_service, edge_service, signal_service)
        b1 = belief_service.create_belief(claim_text="python is great")
        belief_service.update_belief_status(b1.belief_id, BeliefStatus.ACTIVE)

        b2 = belief_service.create_belief(claim_text="rust is great")
        signal_service.emit("belief_proposed", {"belief_id": str(b2.belief_id)})

        result = agent.run()
        assert len(result) == 0

    def test_run_detects_contradiction(self, belief_service, edge_service, signal_service):
        """Contradicting beliefs should be challenged."""
        agent = self._make_agent(belief_service, edge_service, signal_service)

        # Create an active belief
        b1 = belief_service.create_belief(claim_text="python is fast")
        belief_service.update_belief_status(b1.belief_id, BeliefStatus.ACTIVE)

        # Create a contradicting proposed belief
        b2 = belief_service.create_belief(claim_text="python is not fast")
        signal_service.emit("belief_proposed", {"belief_id": str(b2.belief_id)})

        result = agent.run()
        assert b1.belief_id in result

        # Verify b1 is now challenged
        updated = belief_service.get_belief(b1.belief_id)
        assert updated.status == BeliefStatus.CHALLENGED

    def test_run_creates_contradicts_edge(self, belief_service, edge_service, signal_service):
        """A contradicts edge should be created between conflicting beliefs."""
        agent = self._make_agent(belief_service, edge_service, signal_service)

        b1 = belief_service.create_belief(claim_text="python is fast")
        belief_service.update_belief_status(b1.belief_id, BeliefStatus.ACTIVE)

        b2 = belief_service.create_belief(claim_text="python is not fast")
        signal_service.emit("belief_proposed", {"belief_id": str(b2.belief_id)})

        agent.run()

        edges = edge_service.get_edges(
            EntityType.BELIEF, b1.belief_id, direction="incoming", rel_type=RelType.CONTRADICTS
        )
        assert len(edges) >= 1

    def test_run_emits_belief_challenged_signal(
        self, belief_service, edge_service, signal_service
    ):
        """A belief_challenged signal should be emitted."""
        agent = self._make_agent(belief_service, edge_service, signal_service)

        b1 = belief_service.create_belief(claim_text="python is fast")
        belief_service.update_belief_status(b1.belief_id, BeliefStatus.ACTIVE)

        b2 = belief_service.create_belief(claim_text="python is not fast")
        signal_service.emit("belief_proposed", {"belief_id": str(b2.belief_id)})

        agent.run()

        challenged_signals = signal_service.get_unprocessed("belief_challenged")
        assert len(challenged_signals) >= 1

    def test_run_marks_signals_processed(self, belief_service, edge_service, signal_service):
        """Processed belief_proposed signals should be marked."""
        agent = self._make_agent(belief_service, edge_service, signal_service)

        b = belief_service.create_belief(claim_text="standalone belief")
        signal_service.emit("belief_proposed", {"belief_id": str(b.belief_id)})

        agent.run()

        unprocessed = signal_service.get_unprocessed("belief_proposed")
        assert len(unprocessed) == 0
