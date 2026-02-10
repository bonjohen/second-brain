"""Append-only audit log service."""

from __future__ import annotations

import json
import uuid
from typing import Any

from second_brain.core.models import AuditEntry
from second_brain.storage.sqlite import Database


class AuditService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def log_event(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        action: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Append an entry to the audit log."""
        entry = AuditEntry(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            before=before,
            after=after,
        )
        self._db.execute(
            """
            INSERT INTO audit_log
                (audit_id, entity_type, entity_id, action, before_json, after_json, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(entry.audit_id),
                entry.entity_type,
                str(entry.entity_id),
                entry.action,
                json.dumps(entry.before) if entry.before is not None else None,
                json.dumps(entry.after) if entry.after is not None else None,
                entry.timestamp.isoformat(),
            ),
        )
        return entry

    def get_history(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> list[AuditEntry]:
        """Return all audit entries for a given entity, ordered by timestamp ascending."""
        rows = self._db.fetchall(
            """
            SELECT audit_id, entity_type, entity_id, action, before_json, after_json, timestamp
            FROM audit_log
            WHERE entity_type = ? AND entity_id = ?
            ORDER BY timestamp ASC
            """,
            (entity_type, str(entity_id)),
        )
        return [self._row_to_entry(row) for row in rows]

    @staticmethod
    def _row_to_entry(row: Any) -> AuditEntry:
        return AuditEntry(
            audit_id=uuid.UUID(row["audit_id"]),
            entity_type=row["entity_type"],
            entity_id=uuid.UUID(row["entity_id"]),
            action=row["action"],
            before=json.loads(row["before_json"]) if row["before_json"] else None,
            after=json.loads(row["after_json"]) if row["after_json"] else None,
            timestamp=row["timestamp"],
        )
