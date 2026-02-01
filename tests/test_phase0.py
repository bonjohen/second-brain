"""Phase 0 tests — schema, persistence, FTS, immutability, audit."""

from __future__ import annotations

import pytest

from second_brain.agents.ingestion import IngestionAgent
from second_brain.core.models import ContentType, SourceKind
from second_brain.core.services.audit import AuditService
from second_brain.core.services.notes import NoteService
from second_brain.core.services.signals import SignalService
from second_brain.storage.migrations.runner import ensure_schema
from second_brain.storage.sqlite import Database


@pytest.fixture
def db(tmp_path):
    """Fresh in-memory-like DB for each test."""
    db = Database(tmp_path / "test.db")
    ensure_schema(db)
    yield db
    db.close()


# ── Schema tests ─────────────────────────────────────────────────────────────


class TestSchema:
    def test_tables_created(self, db: Database):
        rows = db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        names = {r["name"] for r in rows}
        assert "notes" in names
        assert "sources" in names
        assert "beliefs" in names
        assert "edges" in names
        assert "signals" in names
        assert "audit_log" in names
        assert "_migrations" in names

    def test_fts_table_created(self, db: Database):
        rows = db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='notes_fts'"
        )
        assert len(rows) == 1

    def test_foreign_keys_enforced(self, db: Database):
        result = db.fetchone("PRAGMA foreign_keys")
        assert result[0] == 1

    def test_wal_mode(self, db: Database):
        result = db.fetchone("PRAGMA journal_mode")
        assert result[0] == "wal"

    def test_migration_idempotent(self, db: Database):
        """Running migrations again should be a no-op."""
        from second_brain.storage.migrations.runner import run_all
        applied = run_all(db)
        assert applied == []  # Already applied


# ── Note + Source persistence ────────────────────────────────────────────────


class TestNotePersistence:
    def test_create_source(self, db: Database):
        svc = NoteService(db)
        source = svc.create_source()
        assert source.source_id
        assert source.kind == SourceKind.USER

        fetched = svc.get_source(source.source_id)
        assert fetched is not None
        assert fetched.source_id == source.source_id

    def test_create_note(self, db: Database):
        svc = NoteService(db)
        source = svc.create_source()
        note = svc.create_note(
            content="Python is great for prototyping",
            source_id=source.source_id,
            tags=["python", "dev"],
        )
        assert note.note_id
        assert note.content_hash  # sha256 computed
        assert note.tags == ["python", "dev"]

        fetched = svc.get_note(note.note_id)
        assert fetched is not None
        assert fetched.content == "Python is great for prototyping"
        assert fetched.content_hash == note.content_hash

    def test_note_content_hash_deterministic(self, db: Database):
        svc = NoteService(db)
        source = svc.create_source()
        n1 = svc.create_note(content="same content", source_id=source.source_id)
        n2 = svc.create_note(content="same content", source_id=source.source_id)
        assert n1.content_hash == n2.content_hash

    def test_list_notes(self, db: Database):
        svc = NoteService(db)
        source = svc.create_source()
        svc.create_note(content="note 1", source_id=source.source_id)
        svc.create_note(content="note 2", source_id=source.source_id)
        notes = svc.list_notes()
        assert len(notes) == 2

    def test_note_foreign_key_constraint(self, db: Database):
        """Cannot create a note with a non-existent source_id."""
        svc = NoteService(db)
        with pytest.raises(Exception):
            svc.create_note(content="orphan", source_id="nonexistent-uuid")


# ── FTS search ───────────────────────────────────────────────────────────────


class TestFTSSearch:
    def test_basic_search(self, db: Database):
        svc = NoteService(db)
        source = svc.create_source()
        svc.create_note(content="Machine learning is transforming healthcare", source_id=source.source_id)
        svc.create_note(content="Python is great for data science", source_id=source.source_id)
        svc.create_note(content="Healthcare costs are rising", source_id=source.source_id)

        results = svc.search_notes("healthcare")
        assert len(results) == 2

    def test_no_results(self, db: Database):
        svc = NoteService(db)
        source = svc.create_source()
        svc.create_note(content="Something unrelated", source_id=source.source_id)
        results = svc.search_notes("quantum")
        assert len(results) == 0


# ── Signal service ───────────────────────────────────────────────────────────


class TestSignals:
    def test_emit_and_consume(self, db: Database):
        svc = SignalService(db)
        sig = svc.emit("new_note", {"note_id": "abc123"})
        assert sig.signal_id
        assert sig.processed_at is None

        pending = svc.consume_pending("new_note")
        assert len(pending) == 1
        assert pending[0].signal_id == sig.signal_id

    def test_mark_processed(self, db: Database):
        svc = SignalService(db)
        sig = svc.emit("test_signal")
        svc.mark_processed(sig.signal_id)

        pending = svc.consume_pending("test_signal")
        assert len(pending) == 0

    def test_filter_by_type(self, db: Database):
        svc = SignalService(db)
        svc.emit("type_a")
        svc.emit("type_b")
        svc.emit("type_a")

        assert len(svc.consume_pending("type_a")) == 2
        assert len(svc.consume_pending("type_b")) == 1


# ── Audit service ────────────────────────────────────────────────────────────


class TestAudit:
    def test_log_and_retrieve(self, db: Database):
        svc = AuditService(db)
        entry = svc.log("note", "note-123", "create", new_value={"content": "hello"})
        assert entry.audit_id

        history = svc.get_history("note", "note-123")
        assert len(history) == 1
        assert history[0].action == "create"
        assert history[0].new_value == {"content": "hello"}

    def test_recent(self, db: Database):
        svc = AuditService(db)
        svc.log("note", "n1", "create")
        svc.log("source", "s1", "create")
        recent = svc.get_recent(limit=10)
        assert len(recent) == 2


# ── Ingestion agent ─────────────────────────────────────────────────────────


class TestIngestionAgent:
    def test_full_pipeline(self, db: Database):
        agent = IngestionAgent(db)
        result = agent.ingest(
            content="This is about #machinelearning and John Smith is involved",
        )
        assert result["note_id"]
        assert result["source_id"]
        assert result["content_hash"]
        assert "machinelearning" in result["tags"]
        assert "John Smith" in result["entities"]

        # Verify signal was emitted
        signals = SignalService(db).consume_pending("new_note")
        assert len(signals) == 1

        # Verify audit trail
        audit = AuditService(db)
        note_history = audit.get_history("note", result["note_id"])
        assert len(note_history) == 1

    def test_extra_tags(self, db: Database):
        agent = IngestionAgent(db)
        result = agent.ingest(
            content="Plain text without hashtags",
            extra_tags=["manual-tag", "review"],
        )
        assert "manual-tag" in result["tags"]
        assert "review" in result["tags"]

    def test_content_types(self, db: Database):
        agent = IngestionAgent(db)
        result = agent.ingest(
            content="```python\nprint('hello')\n```",
            content_type=ContentType.CODE,
        )
        note = NoteService(db).get_note(result["note_id"])
        assert note.content_type == ContentType.CODE
