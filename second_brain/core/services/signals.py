"""Signal service — event queue emit/consume pattern."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from second_brain.core.models import Signal
from second_brain.storage.sqlite import Database


class SignalService:
    def __init__(self, db: Database):
        self.db = db

    def emit(self, signal_type: str, payload: dict | None = None) -> Signal:
        """Emit a new signal into the queue."""
        signal = Signal(type=signal_type, payload=payload or {})
        self.db.execute(
            "INSERT INTO signals (signal_id, type, payload, created_at, processed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                signal.signal_id,
                signal.type,
                json.dumps(signal.payload),
                signal.created_at.isoformat(),
                None,
            ),
        )
        self.db.conn.commit()
        return signal

    def consume_pending(self, signal_type: str | None = None, limit: int = 100) -> list[Signal]:
        """Fetch unprocessed signals, optionally filtered by type."""
        if signal_type:
            rows = self.db.fetchall(
                "SELECT * FROM signals WHERE processed_at IS NULL AND type = ? "
                "ORDER BY created_at LIMIT ?",
                (signal_type, limit),
            )
        else:
            rows = self.db.fetchall(
                "SELECT * FROM signals WHERE processed_at IS NULL "
                "ORDER BY created_at LIMIT ?",
                (limit,),
            )
        return [self._row_to_signal(r) for r in rows]

    def mark_processed(self, signal_id: str) -> None:
        """Mark a signal as processed."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE signals SET processed_at = ? WHERE signal_id = ?",
            (now, signal_id),
        )
        self.db.conn.commit()

    def _row_to_signal(self, row) -> Signal:
        return Signal(
            signal_id=row["signal_id"],
            type=row["type"],
            payload=json.loads(row["payload"]),
            created_at=row["created_at"],
            processed_at=row["processed_at"],
        )
