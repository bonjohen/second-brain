"""Signal emission and processing service."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from second_brain.core.models import Signal
from second_brain.storage.sqlite import Database


class SignalService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def emit(self, signal_type: str, payload: dict[str, Any] | None = None) -> Signal:
        """Create and persist a new signal."""
        signal = Signal(type=signal_type, payload=payload or {})
        self._db.execute(
            """
            INSERT INTO signals (signal_id, type, payload, created_at, processed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(signal.signal_id),
                signal.type,
                json.dumps(signal.payload),
                signal.created_at.isoformat(),
                None,
            ),
        )
        return signal

    def get_unprocessed(self, signal_type: str | None = None) -> list[Signal]:
        """Return unprocessed signals, optionally filtered by type."""
        if signal_type:
            rows = self._db.fetchall(
                """
                SELECT signal_id, type, payload, created_at, processed_at
                FROM signals
                WHERE processed_at IS NULL AND type = ?
                ORDER BY created_at ASC
                """,
                (signal_type,),
            )
        else:
            rows = self._db.fetchall(
                """
                SELECT signal_id, type, payload, created_at, processed_at
                FROM signals
                WHERE processed_at IS NULL
                ORDER BY created_at ASC
                """,
            )
        return [self._row_to_signal(row) for row in rows]

    def mark_processed(self, signal_id: uuid.UUID) -> None:
        """Set processed_at to current UTC timestamp."""
        self._db.execute(
            "UPDATE signals SET processed_at = ? WHERE signal_id = ?",
            (datetime.now(UTC).isoformat(), str(signal_id)),
        )

    @staticmethod
    def _row_to_signal(row: Any) -> Signal:
        return Signal(
            signal_id=uuid.UUID(row["signal_id"]),
            type=row["type"],
            payload=json.loads(row["payload"]),
            created_at=row["created_at"],
            processed_at=row["processed_at"] if row["processed_at"] else None,
        )
