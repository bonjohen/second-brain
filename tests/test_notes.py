"""Tests for NoteService."""

import hashlib
import uuid

import pytest

from second_brain.core.models import ContentType, SourceKind, TrustLabel


class TestNoteService:
    def _create_source(self, note_service):
        return note_service.create_source(SourceKind.USER, "test", TrustLabel.USER)

    def test_create_source(self, note_service):
        source = note_service.create_source(SourceKind.USER, "cli:stdin", TrustLabel.USER)
        assert source.kind == SourceKind.USER
        assert source.locator == "cli:stdin"

    def test_get_source(self, note_service):
        source = self._create_source(note_service)
        retrieved = note_service.get_source(source.source_id)
        assert retrieved is not None
        assert retrieved.source_id == source.source_id

    def test_get_source_not_found(self, note_service):
        assert note_service.get_source(uuid.uuid4()) is None

    def test_create_note_computes_hash(self, note_service):
        source = self._create_source(note_service)
        note = note_service.create_note("hello world", ContentType.TEXT, source.source_id)
        expected_hash = hashlib.sha256(b"hello world").hexdigest()
        assert note.content_hash == expected_hash

    def test_create_note_logs_audit(self, note_service, audit_service):
        source = self._create_source(note_service)
        note = note_service.create_note("audited note", ContentType.TEXT, source.source_id)

        history = audit_service.get_history("note", note.note_id)
        assert len(history) == 1
        assert history[0].action == "created"

    def test_get_note(self, note_service):
        source = self._create_source(note_service)
        note = note_service.create_note("retrievable", ContentType.TEXT, source.source_id)

        retrieved = note_service.get_note(note.note_id)
        assert retrieved is not None
        assert retrieved.content == "retrievable"
        assert retrieved.note_id == note.note_id

    def test_get_note_not_found(self, note_service):
        assert note_service.get_note(uuid.uuid4()) is None

    def test_search_notes_finds_match(self, note_service):
        source = self._create_source(note_service)
        note_service.create_note(
            "Python is a great programming language", ContentType.TEXT, source.source_id
        )
        results = note_service.search_notes("Python")
        assert len(results) == 1
        assert "Python" in results[0].content

    def test_search_notes_no_match(self, note_service):
        source = self._create_source(note_service)
        note_service.create_note("hello world", ContentType.TEXT, source.source_id)
        results = note_service.search_notes("nonexistent")
        assert results == []

    def test_search_notes_multiple_results(self, note_service):
        source = self._create_source(note_service)
        note_service.create_note("Python basics tutorial", ContentType.TEXT, source.source_id)
        note_service.create_note("Advanced Python patterns", ContentType.TEXT, source.source_id)
        note_service.create_note("Rust programming guide", ContentType.TEXT, source.source_id)

        results = note_service.search_notes("Python")
        assert len(results) == 2

    def test_list_notes_with_tag_filter(self, note_service):
        source = self._create_source(note_service)
        note_service.create_note(
            "tagged note", ContentType.TEXT, source.source_id, tags=["python", "tutorial"]
        )
        note_service.create_note(
            "other note", ContentType.TEXT, source.source_id, tags=["rust"]
        )

        results = note_service.list_notes(tag="python")
        assert len(results) == 1
        assert results[0].content == "tagged note"

    def test_list_notes_with_entity_filter(self, note_service):
        source = self._create_source(note_service)
        note_service.create_note(
            "about alice", ContentType.TEXT, source.source_id, entities=["alice"]
        )
        note_service.create_note(
            "about bob", ContentType.TEXT, source.source_id, entities=["bob"]
        )

        results = note_service.list_notes(entity="alice")
        assert len(results) == 1
        assert results[0].content == "about alice"

    def test_list_notes_with_content_type_filter(self, note_service):
        source = self._create_source(note_service)
        note_service.create_note("plain text", ContentType.TEXT, source.source_id)
        note_service.create_note("# Markdown", ContentType.MARKDOWN, source.source_id)

        results = note_service.list_notes(content_type=ContentType.MARKDOWN)
        assert len(results) == 1
        assert results[0].content == "# Markdown"

    def test_list_notes_pagination(self, note_service):
        source = self._create_source(note_service)
        for i in range(5):
            note_service.create_note(f"note {i}", ContentType.TEXT, source.source_id)

        page1 = note_service.list_notes(limit=2, offset=0)
        page2 = note_service.list_notes(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0].note_id != page2[0].note_id

    def test_update_source_trust(self, note_service, audit_service):
        source = note_service.create_source(SourceKind.USER, "test", TrustLabel.UNKNOWN)
        updated = note_service.update_source_trust(source.source_id, TrustLabel.TRUSTED)
        assert updated.trust_label == TrustLabel.TRUSTED

        history = audit_service.get_history("source", source.source_id)
        assert any(e.action == "trust_updated" for e in history)

    def test_search_notes_malformed_fts_query(self, note_service):
        """Unbalanced quotes should return empty list, not crash."""
        source = self._create_source(note_service)
        note_service.create_note("some content", ContentType.TEXT, source.source_id)
        results = note_service.search_notes('"')
        assert results == []

    def test_search_notes_special_operators(self, note_service):
        """Invalid FTS5 operator combinations should return empty list."""
        source = self._create_source(note_service)
        note_service.create_note("some content", ContentType.TEXT, source.source_id)
        results = note_service.search_notes("OR AND NOT")
        assert results == []

    def test_update_source_trust_not_found(self, note_service):
        with pytest.raises(ValueError, match="Source not found"):
            note_service.update_source_trust(uuid.uuid4(), TrustLabel.TRUSTED)
