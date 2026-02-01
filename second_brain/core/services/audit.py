"""Audit service — append-only mutation logging."""

from __future__ import annotations

import json
from typing import Any

from second_brain.core.models import AuditEntry
from second_brain.storage.sqlite import Database


class AuditService:
    def __init__(self, db: Database):
        self.db = db

    def log(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Append an audit entry. Never updates or deletes."""
        entry = AuditEntry(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            old_value=old_value,
            new_value=new_value,
        )
        self.db.execute(
            "INSERT INTO audit_log (audit_id, timestamp, entity_type, entity_id, "
            "action, old_value, new_value) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                entry.audit_id,
                entry.timestamp.isoformat(),
                entry.entity_type,
                entry.entity_id,
                entry.action,
                json.dumps(entry.old_value) if entry.old_value else None,
                json.dumps(entry.new_value) if entry.new_value else None,
            ),
        )
        self.db.conn.commit()
        return entry

    def get_history(
        self, entity_type: str, entity_id: str, limit: int = 50
    ) -> list[AuditEntry]:
        """Get audit trail for a specific entity."""
        rows = self.db.fetchall(
            "SELECT * FROM audit_log WHERE entity_type = ? AND entity_id = ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (entity_type, entity_id, limit),
        )
        return [self._row_to_entry(r) for r in rows]

    def get_recent(self, limit: int = 50) -> list[AuditEntry]:
        """Get most recent audit entries across all entities."""
        rows = self.db.fetchall(
            "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        return [self._row_to_entry(r) for r in rows]

    def _row_to_entry(self, row) -> AuditEntry:
        return AuditEntry(
            audit_id=row["audit_id"],
            timestamp=row["timestamp"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            action=row["action"],
            old_value=json.loads(row["old_value"]) if row["old_value"] else None,
            new_value=json.loads(row["new_value"]) if row["new_value"] else None,
        )
