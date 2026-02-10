"""End-to-end tests for the full stack."""

from datetime import UTC, datetime, timedelta

from click.testing import CliRunner

from second_brain.agents.challenger import ChallengerAgent
from second_brain.agents.curator import CuratorAgent
from second_brain.agents.ingestion import IngestionAgent
from second_brain.agents.synthesis import SynthesisAgent
from second_brain.core.models import BeliefStatus, EntityType
from second_brain.core.rules.lifecycle import auto_transition_beliefs
from second_brain.core.services.audit import AuditService
from second_brain.core.services.beliefs import BeliefService
from second_brain.core.services.edges import EdgeService
from second_brain.core.services.notes import NoteService
from second_brain.core.services.signals import SignalService
from second_brain.runtime.scheduler import Scheduler
from second_brain.storage.sqlite import Database


class TestEndToEnd:
    def test_add_search_show_audit(self, tmp_path):
        """Full pipeline: add a note, search for it, show it, verify audit log."""
        from second_brain.cli.main import cli

        db_path = str(tmp_path / "e2e.db")
        runner = CliRunner()

        # Add a note
        result = runner.invoke(cli, ["--db", db_path, "add", "End to end #testing with @pytest"])
        assert result.exit_code == 0
        note_id = result.output.split("Note created: ")[1].strip().split("\n")[0]

        # Search for it
        result = runner.invoke(cli, ["--db", db_path, "search", "testing"])
        assert result.exit_code == 0
        assert note_id in result.output

        # Show it
        result = runner.invoke(cli, ["--db", db_path, "show", note_id])
        assert result.exit_code == 0
        assert "End to end #testing with @pytest" in result.output
        assert "testing" in result.output  # tag
        assert "pytest" in result.output  # entity

        # Verify audit log directly
        db = Database(db_path)
        audit = AuditService(db)
        import uuid

        history = audit.get_history("note", uuid.UUID(note_id))
        assert len(history) == 1
        assert history[0].action == "created"
        db.close()

    def test_persistence_across_restart(self, tmp_path):
        """Verify state survives database close and reopen."""
        db_path = tmp_path / "persist.db"

        # First session: create a note
        db1 = Database(db_path)
        audit1 = AuditService(db1)
        signals1 = SignalService(db1)
        notes1 = NoteService(db1, audit1)
        agent1 = IngestionAgent(notes1, signals1)

        _, note = agent1.ingest("Persistent data survives restarts")
        note_id = note.note_id
        db1.close()

        # Second session: verify the note exists
        db2 = Database(db_path)
        audit2 = AuditService(db2)
        notes2 = NoteService(db2, audit2)

        retrieved = notes2.get_note(note_id)
        assert retrieved is not None
        assert retrieved.content == "Persistent data survives restarts"

        # Verify search works after restart
        results = notes2.search_notes("Persistent")
        assert len(results) == 1

        # Verify audit trail persists
        history = audit2.get_history("note", note_id)
        assert len(history) == 1
        db2.close()

    def test_multiple_notes_shared_tags(self, tmp_path):
        """Add multiple notes with shared tags, verify all are searchable."""
        db_path = tmp_path / "multi.db"
        db = Database(db_path)
        audit = AuditService(db)
        signals = SignalService(db)
        notes = NoteService(db, audit)
        agent = IngestionAgent(notes, signals)

        agent.ingest("First #python note about basics")
        agent.ingest("Second #python note about advanced topics")
        agent.ingest("A #rust note for comparison")

        # Search by content
        python_results = notes.search_notes("python")
        assert len(python_results) == 2

        # Filter by tag
        python_tagged = notes.list_notes(tag="python")
        assert len(python_tagged) == 2

        rust_tagged = notes.list_notes(tag="rust")
        assert len(rust_tagged) == 1

        # Signals emitted for all
        all_signals = signals.get_unprocessed("new_note")
        assert len(all_signals) == 3

        db.close()

    def test_phase1_lifecycle(self, tmp_path):
        """Phase 1 E2E: ingest → synthesize → challenge → ask."""
        db_path = tmp_path / "phase1.db"
        db = Database(db_path)
        audit = AuditService(db)
        signals = SignalService(db)
        notes = NoteService(db, audit)
        edges = EdgeService(db)
        beliefs = BeliefService(db, audit, edges)
        agent = IngestionAgent(notes, signals)

        # 1. Ingest notes with shared tags
        agent.ingest("Python is a versatile language #python")
        agent.ingest("Python has great ecosystem #python")
        agent.ingest("Python is slow for computation #python")

        # 2. Synthesis: should create beliefs from shared tags
        synth = SynthesisAgent(notes, beliefs, edges, signals)
        created_beliefs = synth.run()
        assert len(created_beliefs) >= 1

        # Verify belief exists and has supports edges
        belief = beliefs.get_belief(created_beliefs[0])
        assert belief is not None
        assert belief.status == BeliefStatus.PROPOSED
        assert "python" in belief.claim_text.lower()

        incoming_edges = edges.get_edges(
            EntityType.BELIEF, belief.belief_id, direction="incoming"
        )
        assert len(incoming_edges) >= 2

        # 3. Challenge: create contradicting beliefs
        b_fast = beliefs.create_belief(claim_text="python is fast")
        beliefs.update_belief_status(b_fast.belief_id, BeliefStatus.ACTIVE)
        b_slow = beliefs.create_belief(claim_text="python is not fast")
        signals.emit("belief_proposed", {"belief_id": str(b_slow.belief_id)})

        challenger = ChallengerAgent(beliefs, edges, signals)
        challenged = challenger.run()
        assert b_fast.belief_id in challenged

        # Verify challenged status
        updated_fast = beliefs.get_belief(b_fast.belief_id)
        assert updated_fast.status == BeliefStatus.CHALLENGED

        # 4. Verify audit trail captures the full lifecycle
        fast_history = audit.get_history("belief", b_fast.belief_id)
        actions = [entry.action for entry in fast_history]
        assert "created" in actions
        assert "status_changed" in actions

        db.close()

    def test_phase2_full_lifecycle(self, tmp_path):
        """Phase 2 E2E: ingest → synthesize → lifecycle → curator → scheduler."""
        import uuid

        from second_brain.core.models import RelType

        db_path = tmp_path / "phase2.db"
        db = Database(db_path)
        audit = AuditService(db)
        signals = SignalService(db)
        notes = NoteService(db, audit)
        edges = EdgeService(db)
        beliefs = BeliefService(db, audit, edges)
        agent = IngestionAgent(notes, signals)

        # 1. Ingest notes
        agent.ingest("Rust is memory safe #rust")
        agent.ingest("Rust has zero-cost abstractions #rust")
        agent.ingest("Rust is hard to learn #rust")

        # 2. Synthesis creates beliefs
        synth = SynthesisAgent(notes, beliefs, edges, signals)
        created = synth.run()
        assert len(created) >= 1

        # 3. Auto-lifecycle: proposed with enough support → active
        for bid in created:
            for _ in range(3):
                edges.create_edge(
                    EntityType.NOTE, uuid.uuid4(), RelType.SUPPORTS,
                    EntityType.BELIEF, bid,
                )
        result = auto_transition_beliefs(beliefs, edges)
        assert len(result["activated"]) >= 1

        # 4. Challenge and deprecate
        b = beliefs.create_belief(claim_text="rust is easy", confidence=0.5)
        beliefs.update_belief_status(b.belief_id, BeliefStatus.ACTIVE)
        beliefs.update_belief_status(b.belief_id, BeliefStatus.CHALLENGED)
        for _ in range(5):
            edges.create_edge(
                EntityType.BELIEF, uuid.uuid4(), RelType.CONTRADICTS,
                EntityType.BELIEF, b.belief_id,
            )
        result2 = auto_transition_beliefs(beliefs, edges)
        assert b.belief_id in result2["deprecated"]

        # 5. Curator archives old deprecated beliefs
        curator = CuratorAgent(notes, beliefs, edges, signals, audit, cold_days=0)
        now = datetime.now(UTC) + timedelta(days=1)
        archived = curator.archive_cold_beliefs(now=now)
        assert archived >= 1

        updated_b = beliefs.get_belief(b.belief_id)
        assert updated_b.status == BeliefStatus.ARCHIVED

        # 6. Scheduler runs all agents
        scheduler = Scheduler()
        scheduler.register("curator", curator.run)
        scheduler.register(
            "lifecycle",
            lambda: auto_transition_beliefs(beliefs, edges),
        )
        results = scheduler.run_once()
        assert len(results) == 2

        # 7. Verify audit trail covers full lifecycle
        history = audit.get_history("belief", b.belief_id)
        actions = [entry.action for entry in history]
        assert "created" in actions
        assert "status_changed" in actions

        db.close()
