"""SQLite storage layer -- connection management and migration runner."""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path.home() / ".second_brain" / "brain.db"


class Database:
    """Manages SQLite connections with WAL mode and foreign keys."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path),
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._owner_thread = threading.get_ident()
        self.run_migrations()

    def _check_thread(self) -> None:
        """Raise RuntimeError if called from a thread other than the owner."""
        if threading.get_ident() != self._owner_thread:
            raise RuntimeError(
                "Database accessed from a different thread than the one that created it"
            )

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Yield the connection; commit on success, rollback on error."""
        self._check_thread()
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """Yield a cursor inside an explicit transaction."""
        self._check_thread()
        cursor = self._conn.cursor()
        try:
            cursor.execute("BEGIN")
            yield cursor
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cursor.close()

    def execute(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] = (),
    ) -> sqlite3.Cursor:
        """Execute a single SQL statement and commit."""
        self._check_thread()
        cursor = self._conn.execute(sql, params)
        self._conn.commit()
        return cursor

    def fetchone(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] = (),
    ) -> sqlite3.Row | None:
        """Execute SQL and return first row or None."""
        self._check_thread()
        return self._conn.execute(sql, params).fetchone()

    def fetchall(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] = (),
    ) -> list[sqlite3.Row]:
        """Execute SQL and return all rows."""
        self._check_thread()
        return self._conn.execute(sql, params).fetchall()

    def run_migrations(self) -> None:
        """Apply unapplied migrations in order."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id         INTEGER PRIMARY KEY,
                filename   TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

        applied = {
            row[0]
            for row in self._conn.execute("SELECT filename FROM _migrations").fetchall()
        }

        migrations_dir = Path(__file__).parent / "migrations"
        if not migrations_dir.exists():
            return

        for mf in sorted(migrations_dir.glob("*.sql")):
            if mf.name not in applied:
                sql = mf.read_text(encoding="utf-8")
                try:
                    # Note: executescript() auto-commits per statement, so partial
                    # DDL may be applied on failure. Use CREATE TABLE/INDEX IF NOT
                    # EXISTS in migration files to make them re-runnable.
                    self._conn.executescript(sql)
                except Exception:
                    logger.exception("Migration %s failed", mf.name)
                    raise RuntimeError(
                        f"Migration {mf.name} failed. Partial DDL may have been applied. "
                        "Use IF NOT EXISTS guards in migrations for safe re-runs."
                    ) from None
                self._conn.execute(
                    "INSERT INTO _migrations (filename, applied_at) VALUES (?, ?)",
                    (mf.name, datetime.now(UTC).isoformat()),
                )
                self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
