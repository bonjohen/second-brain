"""Tests for the CuratorAgent."""

from datetime import UTC, datetime, timedelta

from second_brain.agents.curator import CuratorAgent
from second_brain.core.models import BeliefStatus


class TestCuratorAgent:
    def _make_agent(
        self, note_service, belief_service, edge_service, signal_service, audit_service,
        cold_days=90,
    ):
        return CuratorAgent(
            note_service, belief_service, edge_service,
            signal_service, audit_service,
            cold_days=cold_days,
        )

    def test_run_empty_system(
        self, note_service, belief_service, edge_service, signal_service, audit_service
    ):
        agent = self._make_agent(
            note_service, belief_service, edge_service, signal_service, audit_service
        )
        result = agent.run()
        assert result == {"archived": 0, "deduplicated": 0, "distilled": 0}

    def test_archive_cold_beliefs(
        self, note_service, belief_service, edge_service, signal_service, audit_service
    ):
        """Deprecated beliefs older than cold_days should be archived."""
        agent = self._make_agent(
            note_service, belief_service, edge_service,
            signal_service, audit_service, cold_days=1,
        )

        # Create and deprecate a belief
        b = belief_service.create_belief(claim_text="old belief")
        belief_service.update_belief_status(b.belief_id, BeliefStatus.ACTIVE)
        belief_service.update_belief_status(b.belief_id, BeliefStatus.CHALLENGED)
        belief_service.update_belief_status(b.belief_id, BeliefStatus.DEPRECATED)

        # Simulate passage of time
        now = datetime.now(UTC) + timedelta(days=2)
        archived = agent.archive_cold_beliefs(now=now)
        assert archived == 1

        updated = belief_service.get_belief(b.belief_id)
        assert updated.status == BeliefStatus.ARCHIVED

    def test_archive_skips_recent(
        self, note_service, belief_service, edge_service, signal_service, audit_service
    ):
        """Recently deprecated beliefs should not be archived."""
        agent = self._make_agent(
            note_service, belief_service, edge_service,
            signal_service, audit_service, cold_days=90,
        )

        b = belief_service.create_belief(claim_text="recent belief")
        belief_service.update_belief_status(b.belief_id, BeliefStatus.ACTIVE)
        belief_service.update_belief_status(b.belief_id, BeliefStatus.CHALLENGED)
        belief_service.update_belief_status(b.belief_id, BeliefStatus.DEPRECATED)

        archived = agent.archive_cold_beliefs()
        assert archived == 0

    def test_distill_notes_creates_summary(
        self, note_service, belief_service, edge_service, signal_service, audit_service
    ):
        """Tags with 5+ notes should produce a summary note."""
        agent = self._make_agent(
            note_service, belief_service, edge_service, signal_service, audit_service
        )

        source = note_service.create_source(kind="user", locator="test")
        for i in range(6):
            note_service.create_note(
                f"Python note {i} about programming",
                content_type="text",
                source_id=source.source_id,
                tags=["python"],
            )

        distilled = agent.distill_notes()
        assert distilled == 1

        # Verify summary note was created
        summaries = note_service.list_notes(tag="distill-python")
        assert len(summaries) == 1
        assert "Summary of" in summaries[0].content

    def test_distill_skips_small_groups(
        self, note_service, belief_service, edge_service, signal_service, audit_service
    ):
        """Tags with fewer than 5 notes should not be distilled."""
        agent = self._make_agent(
            note_service, belief_service, edge_service, signal_service, audit_service
        )

        source = note_service.create_source(kind="user", locator="test")
        for i in range(3):
            note_service.create_note(
                f"Small group note {i}",
                content_type="text",
                source_id=source.source_id,
                tags=["small"],
            )

        distilled = agent.distill_notes()
        assert distilled == 0

    def test_distill_idempotent(
        self, note_service, belief_service, edge_service, signal_service, audit_service
    ):
        """Running distill twice should not create duplicate summaries."""
        agent = self._make_agent(
            note_service, belief_service, edge_service, signal_service, audit_service
        )

        source = note_service.create_source(kind="user", locator="test")
        for i in range(6):
            note_service.create_note(
                f"Distill idempotent test {i}",
                content_type="text",
                source_id=source.source_id,
                tags=["idem"],
            )

        agent.distill_notes()
        second = agent.distill_notes()
        assert second == 0
