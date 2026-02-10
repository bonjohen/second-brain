"""Note and source persistence service."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import uuid
from typing import Any

from second_brain.core.models import (
    ContentType,
    Note,
    Source,
    SourceKind,
    TrustLabel,
)
from second_brain.core.services.audit import AuditService
from second_brain.core.utils import safe_json_loads
from second_brain.storage.sqlite import Database

logger = logging.getLogger(__name__)


class NoteService:
    def __init__(self, db: Database, audit: AuditService) -> None:
        self._db = db
        self._audit = audit

    def create_source(
        self,
        kind: SourceKind,
        locator: str,
        trust_label: TrustLabel = TrustLabel.UNKNOWN,
    ) -> Source:
        """Create and persist a Source record."""
        source = Source(kind=kind, locator=locator, trust_label=trust_label)
        self._db.execute(
            """
            INSERT INTO sources (source_id, kind, locator, captured_at, trust_label)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(source.source_id),
                source.kind.value,
                source.locator,
                source.captured_at.isoformat(),
                source.trust_label.value,
            ),
        )
        return source

    def get_source(self, source_id: uuid.UUID) -> Source | None:
        """Retrieve a source by ID."""
        row = self._db.fetchone(
            "SELECT * FROM sources WHERE source_id = ?",
            (str(source_id),),
        )
        if row is None:
            return None
        return self._row_to_source(row)

    def update_source_trust(
        self,
        source_id: uuid.UUID,
        new_trust_label: TrustLabel,
    ) -> Source:
        """Update trust label for a source. Raises ValueError if not found."""
        source = self.get_source(source_id)
        if source is None:
            raise ValueError(f"Source not found: {source_id}")

        old_trust = source.trust_label
        self._db.execute(
            "UPDATE sources SET trust_label = ? WHERE source_id = ?",
            (new_trust_label.value, str(source_id)),
        )
        self._audit.log_event(
            entity_type="source",
            entity_id=source_id,
            action="trust_updated",
            before={"trust_label": old_trust.value},
            after={"trust_label": new_trust_label.value},
        )
        return self.get_source(source_id)

    def create_note(
        self,
        content: str,
        content_type: ContentType,
        source_id: uuid.UUID,
        tags: list[str] | None = None,
        entities: list[str] | None = None,
    ) -> Note:
        """Create and persist an immutable Note with SHA-256 hash."""
        content_hash = self._compute_hash(content)
        note = Note(
            content=content,
            content_type=content_type,
            source_id=source_id,
            tags=tags or [],
            entities=entities or [],
            content_hash=content_hash,
        )
        self._db.execute(
            """
            INSERT INTO notes
                (note_id, created_at, content, content_type,
                 source_id, tags, entities, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(note.note_id),
                note.created_at.isoformat(),
                note.content,
                note.content_type.value,
                str(note.source_id),
                json.dumps(note.tags),
                json.dumps(note.entities),
                note.content_hash,
            ),
        )
        self._audit.log_event(
            entity_type="note",
            entity_id=note.note_id,
            action="created",
            after=note.model_dump(mode="json"),
        )
        return note

    def get_note(self, note_id: uuid.UUID) -> Note | None:
        """Retrieve a note by ID."""
        row = self._db.fetchone(
            "SELECT * FROM notes WHERE note_id = ?",
            (str(note_id),),
        )
        if row is None:
            return None
        return self._row_to_note(row)

    def search_notes(self, query: str) -> list[Note]:
        """Full-text search using FTS5."""
        try:
            rows = self._db.fetchall(
                """
                SELECT n.*
                FROM notes n
                JOIN notes_fts ON notes_fts.note_id = n.note_id
                WHERE notes_fts MATCH ?
                ORDER BY rank
                """,
                (query,),
            )
        except sqlite3.OperationalError:
            logger.warning("FTS5 search failed for query %r", query, exc_info=True)
            return []
        return [self._row_to_note(row) for row in rows]

    def list_notes(
        self,
        tag: str | None = None,
        entity: str | None = None,
        content_type: ContentType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Note]:
        """List notes with optional filters."""
        conditions: list[str] = []
        params: list[Any] = []

        if tag:
            conditions.append(
                "EXISTS (SELECT 1 FROM json_each(notes.tags) WHERE json_each.value = ?)"
            )
            params.append(tag.strip().lower())

        if entity:
            conditions.append(
                "EXISTS (SELECT 1 FROM json_each(notes.entities) WHERE json_each.value = ?)"
            )
            params.append(entity.strip().lower())

        if content_type:
            conditions.append("content_type = ?")
            params.append(content_type.value)

        where = ""
        if conditions:
            where = "WHERE " + " AND ".join(conditions)

        params.extend([limit, offset])
        # SAFETY: {where} only contains static SQL fragments built above;
        # all user-supplied values use parameterized ? placeholders in params.
        rows = self._db.fetchall(
            f"SELECT * FROM notes {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            tuple(params),
        )
        return [self._row_to_note(row) for row in rows]

    @staticmethod
    def _compute_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _row_to_note(row: Any) -> Note:
        return Note(
            note_id=uuid.UUID(row["note_id"]),
            created_at=row["created_at"],
            content=row["content"],
            content_type=ContentType(row["content_type"]),
            source_id=uuid.UUID(row["source_id"]),
            tags=safe_json_loads(row["tags"], default=[], context="note.tags"),
            entities=safe_json_loads(row["entities"], default=[], context="note.entities"),
            content_hash=row["content_hash"],
        )

    @staticmethod
    def _row_to_source(row: Any) -> Source:
        return Source(
            source_id=uuid.UUID(row["source_id"]),
            kind=SourceKind(row["kind"]),
            locator=row["locator"],
            captured_at=row["captured_at"],
            trust_label=TrustLabel(row["trust_label"]),
        )
