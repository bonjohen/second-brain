"""IngestionAgent — captures raw input into Source + Note, extracts metadata, emits signals.

Per design.md Section 5.1:
1. Create Source
2. Create immutable Note
3. Extract tags/entities (regex + keyword list only)
4. (Embedding — deferred to Phase 1)
5. Emit signal:new_note
"""

from __future__ import annotations

import re

from second_brain.core.models import ContentType, SourceKind, TrustLabel
from second_brain.core.services.audit import AuditService
from second_brain.core.services.notes import NoteService
from second_brain.core.services.signals import SignalService
from second_brain.storage.sqlite import Database


# Simple regex patterns for tag/entity extraction
_TAG_PATTERN = re.compile(r"#(\w[\w-]*)", re.UNICODE)
_ENTITY_PATTERN = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")  # ProperCase multi-word


class IngestionAgent:
    def __init__(self, db: Database):
        self.db = db
        self.notes = NoteService(db)
        self.signals = SignalService(db)
        self.audit = AuditService(db)

    def ingest(
        self,
        content: str,
        content_type: ContentType = ContentType.TEXT,
        source_kind: SourceKind = SourceKind.USER,
        locator: str = "cli",
        trust_label: TrustLabel = TrustLabel.USER,
        extra_tags: list[str] | None = None,
    ) -> dict:
        """Full ingestion pipeline. Returns dict with source_id, note_id, tags, entities."""
        # 1. Create Source
        source = self.notes.create_source(
            kind=source_kind, locator=locator, trust_label=trust_label
        )
        self.audit.log("source", source.source_id, "create", new_value=source.model_dump(mode="json"))

        # 2. Extract tags and entities
        tags = self._extract_tags(content)
        if extra_tags:
            tags = list(set(tags + extra_tags))
        entities = self._extract_entities(content)

        # 3. Create immutable Note
        note = self.notes.create_note(
            content=content,
            source_id=source.source_id,
            content_type=content_type,
            tags=tags,
            entities=entities,
        )
        self.audit.log("note", note.note_id, "create", new_value=note.model_dump(mode="json"))

        # 4. Emit signal:new_note
        self.signals.emit(
            "new_note",
            {"note_id": note.note_id, "source_id": source.source_id},
        )

        return {
            "source_id": source.source_id,
            "note_id": note.note_id,
            "tags": tags,
            "entities": entities,
            "content_hash": note.content_hash,
        }

    def _extract_tags(self, content: str) -> list[str]:
        """Extract #hashtag patterns from content."""
        return list(set(_TAG_PATTERN.findall(content)))

    def _extract_entities(self, content: str) -> list[str]:
        """Extract Proper Case multi-word entities from content."""
        return list(set(_ENTITY_PATTERN.findall(content)))
