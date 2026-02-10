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

    def test_migration_failure_is_surfaced(self, tmp_path):
        """A broken migration should raise RuntimeError with the filename."""
        import shutil
        from pathlib import Path

        # Copy real migrations, then add a broken one
        real_migrations = (
            Path(__file__).resolve().parent.parent / "second_brain" / "storage" / "migrations"
        )
        custom_migrations = tmp_path / "custom_migrations"
        shutil.copytree(real_migrations, custom_migrations)

        broken = custom_migrations / "999_broken.sql"
        broken.write_text(
            "CREATE TABLE IF NOT EXISTS _test_broken (id INTEGER);\n"
            "THIS IS NOT VALID SQL;\n",
            encoding="utf-8",
        )

        # Bootstrap a healthy DB with all real migrations applied
        db_path = tmp_path / "fail_test.db"
        db = Database(db_path)

        # Helper that mirrors run_migrations() but uses custom_migrations dir
        def run_custom_migrations():
            applied = {
                row[0]
                for row in db._conn.execute("SELECT filename FROM _migrations").fetchall()
            }
            for mf in sorted(custom_migrations.glob("*.sql")):
                if mf.name not in applied:
                    sql = mf.read_text(encoding="utf-8")
                    try:
                        db._conn.executescript(sql)
                    except Exception:
                        raise RuntimeError(
                            f"Migration {mf.name} failed. Partial DDL may have been applied. "
                            "Use IF NOT EXISTS guards in migrations for safe re-runs."
                        ) from None
                    db._conn.execute(
                        "INSERT INTO _migrations (filename, applied_at) VALUES (?, ?)",
                        (mf.name, "2025-01-01T00:00:00"),
                    )
                    db._conn.commit()

        # Broken migration raises RuntimeError
        with pytest.raises(RuntimeError, match="999_broken.sql"):
            run_custom_migrations()

        # Partial DDL (CREATE TABLE) was applied by executescript
        row = db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_test_broken'"
        )
        assert row is not None

        # But the migration was NOT recorded
        recorded = db.fetchone(
            "SELECT filename FROM _migrations WHERE filename = '999_broken.sql'"
        )
        assert recorded is None

        # Recovery: fix the migration and re-run
        broken.write_text(
            "CREATE TABLE IF NOT EXISTS _test_broken (id INTEGER);\n",
            encoding="utf-8",
        )
        run_custom_migrations()
        recorded = db.fetchone(
            "SELECT filename FROM _migrations WHERE filename = '999_broken.sql'"
        )
        assert recorded is not None

        db.close()
