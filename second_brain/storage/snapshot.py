"""Snapshot and restore — SQLite database backup and recovery.

Per design.md Section 9.2: Snapshot + restore commands.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def create_snapshot(db_path: Path, snapshot_dir: Path | None = None) -> Path:
    """Create a full copy of the database file.

    Returns the path to the snapshot file.
    """
    if snapshot_dir is None:
        snapshot_dir = db_path.parent / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    snapshot_path = snapshot_dir / f"brain_{timestamp}.db"

    # Use SQLite's backup API for consistency
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(snapshot_path))
    src.backup(dst)
    dst.close()
    src.close()

    return snapshot_path


def restore_snapshot(snapshot_path: Path, db_path: Path) -> None:
    """Restore a database from a snapshot file.

    Creates a backup of the current DB before restoring.
    """
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")

    # Backup current before restoring
    if db_path.exists():
        backup_path = db_path.with_suffix(".db.pre_restore")
        shutil.copy2(db_path, backup_path)

    src = sqlite3.connect(str(snapshot_path))
    dst = sqlite3.connect(str(db_path))
    src.backup(dst)
    dst.close()
    src.close()


def list_snapshots(db_path: Path) -> list[Path]:
    """List available snapshots sorted by date (newest first)."""
    snapshot_dir = db_path.parent / "snapshots"
    if not snapshot_dir.exists():
        return []
    return sorted(snapshot_dir.glob("brain_*.db"), reverse=True)
