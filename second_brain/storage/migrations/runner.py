"""Custom SQLite migration runner with version tracking.

Migrations are numbered SQL files in this directory (e.g. 001_initial_schema.sql).
The runner tracks which have been applied in a _migrations table.
"""

from __future__ import annotations

from pathlib import Path

from second_brain.storage.sqlite import Database

MIGRATIONS_DIR = Path(__file__).parent


def get_applied(db: Database) -> set[str]:
    """Return set of migration filenames already applied."""
    db.execute(
        "CREATE TABLE IF NOT EXISTS _migrations ("
        "  name TEXT PRIMARY KEY,"
        "  applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")"
    )
    rows = db.fetchall("SELECT name FROM _migrations")
    return {row["name"] for row in rows}


def get_pending(db: Database) -> list[Path]:
    """Return sorted list of migration files not yet applied."""
    applied = get_applied(db)
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return [f for f in files if f.name not in applied]


def run_all(db: Database) -> list[str]:
    """Apply all pending migrations. Returns list of applied names."""
    applied_names: list[str] = []
    for migration_file in get_pending(db):
        sql = migration_file.read_text(encoding="utf-8")
        with db.transaction() as cursor:
            cursor.executescript(sql)
            cursor.execute(
                "INSERT INTO _migrations (name) VALUES (?)",
                (migration_file.name,),
            )
        applied_names.append(migration_file.name)
    return applied_names


def ensure_schema(db: Database) -> None:
    """Ensure all migrations are applied. Call on startup."""
    run_all(db)
