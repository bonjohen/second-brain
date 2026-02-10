"""Tests for SQLite storage layer and migrations."""

import sqlite3
import threading

import pytest

from second_brain.storage.sqlite import Database


class TestDatabase:
    def test_creates_file_and_parents(self, tmp_path):
        db_path = tmp_path / "sub" / "dir" / "brain.db"
        db = Database(db_path)
        assert db_path.exists()
        db.close()

    def test_wal_mode(self, db):
        row = db.fetchone("PRAGMA journal_mode")
        assert row[0] == "wal"

    def test_foreign_keys_enabled(self, db):
        row = db.fetchone("PRAGMA foreign_keys")
        assert row[0] == 1

    def test_tables_exist(self, db):
        rows = db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        names = {row["name"] for row in rows}
        assert {"sources", "notes", "signals", "audit_log", "_migrations"} <= names

    def test_phase1_tables_exist(self, db):
        rows = db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        names = {row["name"] for row in rows}
        assert {"beliefs", "edges", "embeddings"} <= names

    def test_fts5_table_exists(self, db):
        rows = db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = 'notes_fts'"
        )
        assert len(rows) == 1

    def test_migrations_recorded(self, db):
        rows = db.fetchall("SELECT filename FROM _migrations ORDER BY filename")
        filenames = [row["filename"] for row in rows]
        assert "001_initial_schema.sql" in filenames
        assert "002_fts5.sql" in filenames
        assert "003_beliefs.sql" in filenames
        assert "004_edges.sql" in filenames
        assert "005_embeddings.sql" in filenames

    def test_foreign_key_enforcement(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                INSERT INTO notes
                    (note_id, created_at, content, content_type,
                     source_id, tags, entities, content_hash)
                VALUES ('fake-id', '2025-01-01', 'test', 'text',
                        'nonexistent-source', '[]', '[]', 'abc')
                """
            )

    def test_connection_context_manager_commits(self, db):
        with db.connection():
            db._conn.execute(
                """
                INSERT INTO sources (source_id, kind, locator, captured_at, trust_label)
                VALUES ('test-src', 'user', 'test', '2025-01-01', 'user')
                """
            )
        row = db.fetchone("SELECT * FROM sources WHERE source_id = 'test-src'")
        assert row is not None

    def test_connection_context_manager_rollback_on_error(self, db):
        with pytest.raises(sqlite3.IntegrityError), db.connection():
            db._conn.execute(
                """
                    INSERT INTO sources (source_id, kind, locator, captured_at, trust_label)
                    VALUES ('rollback-test', 'user', 'test', '2025-01-01', 'user')
                    """
            )
            # This should fail and trigger rollback of the whole block
            db._conn.execute(
                """
                    INSERT INTO sources (source_id, kind, locator, captured_at, trust_label)
                    VALUES ('rollback-test', 'user', 'test', '2025-01-01', 'user')
                    """
            )
        row = db.fetchone("SELECT * FROM sources WHERE source_id = 'rollback-test'")
        assert row is None

    def test_transaction_context_manager(self, db):
        with db.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO sources (source_id, kind, locator, captured_at, trust_label)
                VALUES ('txn-test', 'user', 'test', '2025-01-01', 'user')
                """
            )
        row = db.fetchone("SELECT * FROM sources WHERE source_id = 'txn-test'")
        assert row is not None

    def test_beliefs_status_check_constraint(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                INSERT INTO beliefs
                    (belief_id, claim_text, status, confidence, created_at, updated_at,
                     decay_model, scope, derived_from_agent)
                VALUES ('test-b', 'claim', 'invalid_status', 0.5, '2025-01-01', '2025-01-01',
                        'exponential', '{}', '')
                """
            )

    def test_beliefs_confidence_check_constraint(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                INSERT INTO beliefs
                    (belief_id, claim_text, status, confidence, created_at, updated_at,
                     decay_model, scope, derived_from_agent)
                VALUES ('test-b2', 'claim', 'proposed', 1.5, '2025-01-01', '2025-01-01',
                        'exponential', '{}', '')
                """
            )

    def test_edges_rel_type_check_constraint(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                INSERT INTO edges (edge_id, from_type, from_id, rel_type, to_type, to_id)
                VALUES ('test-e', 'note', 'id1', 'invalid_rel', 'belief', 'id2')
                """
            )

    def test_edges_from_type_check_constraint(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                INSERT INTO edges (edge_id, from_type, from_id, rel_type, to_type, to_id)
                VALUES ('test-e2', 'invalid_type', 'id1', 'supports', 'belief', 'id2')
                """
            )

    def test_rejects_cross_thread_access(self, tmp_path):
        db = Database(tmp_path / "thread_test.db")
        error = None

        def bg():
            nonlocal error
            try:
                db.execute("SELECT 1")
            except RuntimeError as exc:
                error = exc

        t = threading.Thread(target=bg)
        t.start()
        t.join()
        db.close()
        assert error is not None
        assert "different thread" in str(error)
