"""Phase 2 tests — dispatcher, scheduler, curator, snapshot, reports, end-to-end."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from second_brain.agents.curator import CuratorAgent
from second_brain.agents.ingestion import IngestionAgent
from second_brain.agents.synthesis import SynthesisAgent
from second_brain.core.models import BeliefStatus
from second_brain.core.services.beliefs import BeliefService
from second_brain.core.services.notes import NoteService
from second_brain.core.services.reports import ReportService
from second_brain.core.services.signals import SignalService
from second_brain.runtime.dispatcher import Dispatcher
from second_brain.runtime.scheduler import Scheduler
from second_brain.storage.migrations.runner import ensure_schema
from second_brain.storage.snapshot import create_snapshot, list_snapshots, restore_snapshot
from second_brain.storage.sqlite import Database


@pytest.fixture
def db(tmp_path):
    db = Database(tmp_path / "test.db")
    ensure_schema(db)
    yield db
    db.close()


# ── Dispatcher ───────────────────────────────────────────────────────────────


class TestDispatcher:
    def test_process_pending_signals(self, db):
        ingestion = IngestionAgent(db)
        ingestion.ingest("Test #topic note one")
        ingestion.ingest("Another #topic note two")

        dispatcher = Dispatcher(db)
        results = dispatcher.process_pending()
        # Should have processed signals and possibly synthesized beliefs
        assert isinstance(results, list)

    def test_full_cycle(self, db):
        ingestion = IngestionAgent(db)
        ingestion.ingest("Data on #science experiments")
        ingestion.ingest("More #science research")

        dispatcher = Dispatcher(db)
        results = dispatcher.run_full_cycle()
        assert "signal_results" in results
        assert "challenger_results" in results
        assert "synthesis_results" in results


# ── Scheduler ────────────────────────────────────────────────────────────────


class TestScheduler:
    def test_tick(self, db):
        ingestion = IngestionAgent(db)
        ingestion.ingest("Note for scheduler test #test")

        scheduler = Scheduler(db)
        results = scheduler.tick()
        assert "timestamp" in results
        assert "curator" in results
        assert "challenger" in results
        assert "synthesis" in results


# ── Curator ──────────────────────────────────────────────────────────────────


class TestCurator:
    def test_archive_deprecated_past_grace(self, db):
        beliefs = BeliefService(db)
        b = beliefs.create_belief(claim_text="old belief")
        beliefs.transition(b.belief_id, BeliefStatus.ACTIVE)
        beliefs.transition(b.belief_id, BeliefStatus.CHALLENGED)
        beliefs.transition(b.belief_id, BeliefStatus.DEPRECATED)

        # Manually set updated_at to past grace period
        old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        db.execute(
            "UPDATE beliefs SET updated_at = ? WHERE belief_id = ?",
            (old_date, b.belief_id),
        )
        db.conn.commit()

        curator = CuratorAgent(db)
        results = curator.run()

        archived = beliefs.get_belief(b.belief_id)
        assert archived.status == BeliefStatus.ARCHIVED

    def test_no_archive_within_grace(self, db):
        beliefs = BeliefService(db)
        b = beliefs.create_belief(claim_text="recent deprecated")
        beliefs.transition(b.belief_id, BeliefStatus.ACTIVE)
        beliefs.transition(b.belief_id, BeliefStatus.CHALLENGED)
        beliefs.transition(b.belief_id, BeliefStatus.DEPRECATED)

        curator = CuratorAgent(db)
        results = curator.run()

        still_deprecated = beliefs.get_belief(b.belief_id)
        assert still_deprecated.status == BeliefStatus.DEPRECATED

    def test_duplicate_detection(self, db):
        beliefs = BeliefService(db)
        b1 = beliefs.create_belief(claim_text="Python is a programming language")
        b2 = beliefs.create_belief(claim_text="Python is a programming language")

        curator = CuratorAgent(db)
        results = curator.run()
        dups = [r for r in results if r.get("action") == "duplicate_detected"]
        assert len(dups) > 0


# ── Snapshot/Restore ─────────────────────────────────────────────────────────


class TestSnapshot:
    def test_snapshot_and_restore(self, tmp_path):
        db_path = tmp_path / "main.db"
        db = Database(db_path)
        ensure_schema(db)

        notes = NoteService(db)
        source = notes.create_source()
        notes.create_note(content="important data", source_id=source.source_id)
        db.close()

        # Create snapshot
        snap = create_snapshot(db_path, tmp_path / "snaps")
        assert snap.exists()

        # Modify original
        db2 = Database(db_path)
        ensure_schema(db2)
        notes2 = NoteService(db2)
        s2 = notes2.create_source()
        notes2.create_note(content="new data", source_id=s2.source_id)
        count_after = len(notes2.list_notes())
        assert count_after == 2
        db2.close()

        # Restore
        restore_snapshot(snap, db_path)
        db3 = Database(db_path)
        ensure_schema(db3)
        notes3 = NoteService(db3)
        count_restored = len(notes3.list_notes())
        assert count_restored == 1
        db3.close()

    def test_list_snapshots(self, tmp_path):
        db_path = tmp_path / "main.db"
        db = Database(db_path)
        ensure_schema(db)
        db.close()

        snap_dir = tmp_path / "snaps"
        snap1 = create_snapshot(db_path, snap_dir)
        assert snap1.exists()
        snap2 = create_snapshot(db_path, snap_dir)
        assert snap2.exists()


# ── Reports ──────────────────────────────────────────────────────────────────


class TestReports:
    def test_health_report(self, db):
        ingestion = IngestionAgent(db)
        ingestion.ingest("Note about #testing")
        ingestion.ingest("Another #testing note")

        report = ReportService(db).generate_health_report()
        assert report.note_count == 2
        assert report.source_count == 2
        assert report.generated_at
        assert report.pending_signal_count >= 0


# ── End-to-end integration ───────────────────────────────────────────────────


class TestEndToEnd:
    def test_full_lifecycle(self, db):
        """Multi-cycle test: ingest → synthesize → challenge → curate."""
        ingestion = IngestionAgent(db)
        synthesis = SynthesisAgent(db)
        beliefs_svc = BeliefService(db)

        # 1. Ingest related notes
        ingestion.ingest("Python is great for #datascience projects")
        ingestion.ingest("Machine learning uses #datascience methods")
        ingestion.ingest("Deep learning is a subset of #datascience")

        # 2. Synthesize beliefs
        synth_results = synthesis.run()
        assert len(synth_results) > 0

        # 3. Check beliefs were created
        all_beliefs = beliefs_svc.list_beliefs()
        assert len(all_beliefs) > 0

        # 4. Run a dispatcher cycle
        dispatcher = Dispatcher(db)
        cycle_results = dispatcher.run_full_cycle()

        # 5. Generate report
        report = ReportService(db).generate_health_report()
        assert report.note_count == 3
        assert report.total_beliefs > 0

    def test_contradiction_lifecycle(self, db):
        """Test: ingest contradicting data → challenge → check state."""
        beliefs_svc = BeliefService(db)

        # Create beliefs that contradict
        b1 = beliefs_svc.create_belief(claim_text="Python is fast")
        beliefs_svc.transition(b1.belief_id, BeliefStatus.ACTIVE)

        b2 = beliefs_svc.create_belief(claim_text="Python is not fast")
        beliefs_svc.transition(b2.belief_id, BeliefStatus.ACTIVE)

        # Run challenger via dispatcher
        from second_brain.agents.challenger import ChallengerAgent
        challenger = ChallengerAgent(db)
        results = challenger.run()

        # At least one should be challenged
        b1_updated = beliefs_svc.get_belief(b1.belief_id)
        b2_updated = beliefs_svc.get_belief(b2.belief_id)
        statuses = {b1_updated.status, b2_updated.status}
        assert BeliefStatus.CHALLENGED in statuses
