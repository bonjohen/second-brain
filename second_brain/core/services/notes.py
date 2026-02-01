"""Note + Source service — CRUD with immutability and content hashing."""

from __future__ import annotations

import hashlib
import json

from second_brain.core.models import ContentType, Note, Source, SourceKind, TrustLabel
from second_brain.storage.sqlite import Database


class NoteService:
    def __init__(self, db: Database):
        self.db = db

    # ── Source operations ────────────────────────────────────────────────

    def create_source(
        self,
        kind: SourceKind = SourceKind.USER,
        locator: str = "cli",
        trust_label: TrustLabel = TrustLabel.USER,
    ) -> Source:
        source = Source(kind=kind, locator=locator, trust_label=trust_label)
        self.db.execute(
            "INSERT INTO sources (source_id, kind, locator, captured_at, trust_label) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                source.source_id,
                source.kind.value,
                source.locator,
                source.captured_at.isoformat(),
                source.trust_label.value,
            ),
        )
        self.db.conn.commit()
        return source

    def get_source(self, source_id: str) -> Source | None:
        row = self.db.fetchone("SELECT * FROM sources WHERE source_id = ?", (source_id,))
        if row is None:
            return None
        return Source(
            source_id=row["source_id"],
            kind=SourceKind(row["kind"]),
            locator=row["locator"],
            captured_at=row["captured_at"],
            trust_label=TrustLabel(row["trust_label"]),
        )

    # ── Note operations ──────────────────────────────────────────────────

    def create_note(
        self,
        content: str,
        source_id: str,
        content_type: ContentType = ContentType.TEXT,
        tags: list[str] | None = None,
        entities: list[str] | None = None,
    ) -> Note:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        note = Note(
            content=content,
            content_type=content_type,
            source_id=source_id,
            tags=tags or [],
            entities=entities or [],
            content_hash=content_hash,
        )
        self.db.execute(
            "INSERT INTO notes (note_id, created_at, content, content_type, "
            "source_id, tags, entities, content_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                note.note_id,
                note.created_at.isoformat(),
                note.content,
                note.content_type.value,
                note.source_id,
                json.dumps(note.tags),
                json.dumps(note.entities),
                note.content_hash,
            ),
        )
        self.db.conn.commit()
        return note

    def get_note(self, note_id: str) -> Note | None:
        row = self.db.fetchone("SELECT * FROM notes WHERE note_id = ?", (note_id,))
        if row is None:
            return None
        return self._row_to_note(row)

    def list_notes(self, limit: int = 50, offset: int = 0) -> list[Note]:
        rows = self.db.fetchall(
            "SELECT * FROM notes ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [self._row_to_note(r) for r in rows]

    def search_notes(self, query: str, limit: int = 20) -> list[Note]:
        """Full-text search via FTS5."""
        rows = self.db.fetchall(
            "SELECT n.* FROM notes n "
            "JOIN notes_fts f ON n.rowid = f.rowid "
            "WHERE notes_fts MATCH ? "
            "ORDER BY rank "
            "LIMIT ?",
            (query, limit),
        )
        return [self._row_to_note(r) for r in rows]

    def _row_to_note(self, row) -> Note:
        return Note(
            note_id=row["note_id"],
            created_at=row["created_at"],
            content=row["content"],
            content_type=ContentType(row["content_type"]),
            source_id=row["source_id"],
            tags=json.loads(row["tags"]),
            entities=json.loads(row["entities"]),
            content_hash=row["content_hash"],
        )
