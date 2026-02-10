"""IngestionAgent -- processes raw input into Notes + Sources."""

from __future__ import annotations

import re

from second_brain.core.models import (
    ContentType,
    Note,
    Source,
    SourceKind,
    TrustLabel,
)
from second_brain.core.services.notes import NoteService
from second_brain.core.services.signals import SignalService

TAG_PATTERN = re.compile(r"#(\w[\w/-]*)", re.UNICODE)
ENTITY_PATTERN = re.compile(r"@(\w[\w/.:-]*)", re.UNICODE)


class IngestionAgent:
    """Processes raw content into the Second Brain.

    Pipeline:
    1. Create Source record.
    2. Extract tags (#word) and entities (@word).
    3. Create immutable Note with content_hash.
    4. Compute and store embedding (if vector_store provided).
    5. Emit signal:new_note.
    """

    def __init__(
        self,
        note_service: NoteService,
        signal_service: SignalService,
        vector_store=None,
    ) -> None:
        self._notes = note_service
        self._signals = signal_service
        self._vector_store = vector_store

    def ingest(
        self,
        content: str,
        content_type: ContentType = ContentType.TEXT,
        source_kind: SourceKind = SourceKind.USER,
        locator: str = "cli:stdin",
        trust_label: TrustLabel = TrustLabel.USER,
        extra_tags: list[str] | None = None,
    ) -> tuple[Source, Note]:
        """Full ingestion pipeline. Returns (Source, Note)."""
        source = self._notes.create_source(
            kind=source_kind,
            locator=locator,
            trust_label=trust_label,
        )

        tags = self.extract_tags(content)
        if extra_tags:
            merged = set(tags) | {t.strip().lower() for t in extra_tags if t.strip()}
            tags = sorted(merged)

        entities = self.extract_entities(content)

        note = self._notes.create_note(
            content=content,
            content_type=content_type,
            source_id=source.source_id,
            tags=tags,
            entities=entities,
        )

        if self._vector_store is not None:
            embedding = self._vector_store.compute_embedding(note.content)
            self._vector_store.store_embedding(str(note.note_id), embedding)

        self._signals.emit(
            "new_note",
            {"note_id": str(note.note_id), "source_id": str(source.source_id)},
        )

        return source, note

    @staticmethod
    def extract_tags(content: str) -> list[str]:
        """Extract #hashtag tokens from content. Returns lowercase, deduplicated, sorted."""
        matches = TAG_PATTERN.findall(content)
        return sorted({t.lower() for t in matches})

    @staticmethod
    def extract_entities(content: str) -> list[str]:
        """Extract @entity tokens from content. Returns lowercase, deduplicated, sorted."""
        matches = ENTITY_PATTERN.findall(content)
        return sorted({e.lower() for e in matches})
