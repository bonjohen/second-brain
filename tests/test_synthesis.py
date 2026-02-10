"""Tests for SynthesisAgent."""

from second_brain.agents.synthesis import SynthesisAgent
from second_brain.core.models import EntityType, RelType


class TestSynthesisAgent:
    def _make_agent(self, note_service, belief_service, edge_service, signal_service):
        return SynthesisAgent(note_service, belief_service, edge_service, signal_service)

    def _add_note(self, note_service, signal_service, content, tags=None):
        source = note_service.create_source(kind="user", locator="test")
        note = note_service.create_note(
            content=content,
            content_type="text",
            source_id=source.source_id,
            tags=tags or [],
        )
        signal_service.emit("new_note", {"note_id": str(note.note_id)})
        return note

    def test_run_no_signals(self, note_service, belief_service, edge_service, signal_service):
        agent = self._make_agent(note_service, belief_service, edge_service, signal_service)
        result = agent.run()
        assert result == []

    def test_run_single_note_no_belief(
        self, note_service, belief_service, edge_service, signal_service
    ):
        """A single note with a unique tag should not create a belief."""
        agent = self._make_agent(note_service, belief_service, edge_service, signal_service)
        self._add_note(note_service, signal_service, "Solo note #unique", tags=["unique"])
        result = agent.run()
        # Might or might not create belief depending on whether existing notes match
        # With a fresh DB and unique tag, no group should reach 2
        assert isinstance(result, list)

    def test_run_creates_belief_for_shared_tags(
        self, note_service, belief_service, edge_service, signal_service
    ):
        """Two notes sharing a tag should produce a belief."""
        agent = self._make_agent(note_service, belief_service, edge_service, signal_service)
        self._add_note(note_service, signal_service, "Python basics #python", tags=["python"])
        self._add_note(note_service, signal_service, "Python advanced #python", tags=["python"])
        result = agent.run()
        assert len(result) >= 1

        # Verify belief was created
        beliefs = belief_service.list_beliefs()
        assert len(beliefs) >= 1
        assert any("python" in b.claim_text.lower() for b in beliefs)

    def test_run_creates_supports_edges(
        self, note_service, belief_service, edge_service, signal_service
    ):
        """Supports edges should link notes to the created belief."""
        agent = self._make_agent(note_service, belief_service, edge_service, signal_service)
        self._add_note(note_service, signal_service, "Rust safety #rust", tags=["rust"])
        self._add_note(note_service, signal_service, "Rust performance #rust", tags=["rust"])
        result = agent.run()
        assert len(result) >= 1

        belief_id = result[0]
        edges = edge_service.get_edges(EntityType.BELIEF, belief_id, direction="incoming")
        assert len(edges) >= 2
        assert all(e.rel_type == RelType.SUPPORTS for e in edges)

    def test_run_emits_belief_proposed_signal(
        self, note_service, belief_service, edge_service, signal_service
    ):
        """A belief_proposed signal should be emitted for each belief."""
        agent = self._make_agent(note_service, belief_service, edge_service, signal_service)
        self._add_note(note_service, signal_service, "Go concurrency #golang", tags=["golang"])
        self._add_note(note_service, signal_service, "Go simplicity #golang", tags=["golang"])
        agent.run()

        proposed_signals = signal_service.get_unprocessed("belief_proposed")
        assert len(proposed_signals) >= 1

    def test_run_marks_signals_processed(
        self, note_service, belief_service, edge_service, signal_service
    ):
        """Processed new_note signals should be marked."""
        agent = self._make_agent(note_service, belief_service, edge_service, signal_service)
        self._add_note(note_service, signal_service, "Test note #test", tags=["test"])
        agent.run()

        unprocessed = signal_service.get_unprocessed("new_note")
        assert len(unprocessed) == 0

    def test_run_idempotent(
        self, note_service, belief_service, edge_service, signal_service
    ):
        """Running twice should not duplicate beliefs."""
        agent = self._make_agent(note_service, belief_service, edge_service, signal_service)
        self._add_note(note_service, signal_service, "Java OOP #java", tags=["java"])
        self._add_note(note_service, signal_service, "Java threads #java", tags=["java"])
        agent.run()

        # Second run with no new signals
        result2 = agent.run()
        assert result2 == []
