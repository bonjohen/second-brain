"""Tests for core Pydantic models and enums."""

import uuid

import pytest
from pydantic import ValidationError

from second_brain.core.models import (
    AuditEntry,
    ContentType,
    Note,
    Signal,
    Source,
    SourceKind,
    TrustLabel,
)


class TestEnums:
    def test_content_type_values(self):
        assert set(ContentType) == {
            ContentType.TEXT,
            ContentType.MARKDOWN,
            ContentType.PDF,
            ContentType.TRANSCRIPT,
            ContentType.CODE,
        }

    def test_source_kind_values(self):
        assert set(SourceKind) == {
            SourceKind.USER,
            SourceKind.FILE,
            SourceKind.URL,
            SourceKind.CLIPBOARD,
        }

    def test_trust_label_values(self):
        assert set(TrustLabel) == {
            TrustLabel.USER,
            TrustLabel.TRUSTED,
            TrustLabel.UNKNOWN,
        }


class TestSource:
    def test_create_source(self):
        s = Source(kind=SourceKind.USER, locator="cli:stdin")
        assert isinstance(s.source_id, uuid.UUID)
        assert s.kind == SourceKind.USER
        assert s.trust_label == TrustLabel.UNKNOWN

    def test_source_is_frozen(self):
        s = Source(kind=SourceKind.USER, locator="cli:stdin")
        with pytest.raises(ValidationError):
            s.locator = "changed"


class TestNote:
    def test_create_note(self):
        sid = uuid.uuid4()
        n = Note(content="hello world", source_id=sid)
        assert isinstance(n.note_id, uuid.UUID)
        assert n.content == "hello world"
        assert n.content_type == ContentType.TEXT
        assert n.tags == []
        assert n.entities == []

    def test_empty_content_rejected(self):
        with pytest.raises(ValidationError, match="must not be empty"):
            Note(content="", source_id=uuid.uuid4())

    def test_whitespace_only_content_rejected(self):
        with pytest.raises(ValidationError, match="must not be empty"):
            Note(content="   \n  ", source_id=uuid.uuid4())

    def test_tags_normalized(self):
        n = Note(content="test", source_id=uuid.uuid4(), tags=["Python", " RUST ", ""])
        assert n.tags == ["python", "rust"]

    def test_entities_normalized(self):
        n = Note(content="test", source_id=uuid.uuid4(), entities=["Alice", " BOB "])
        assert n.entities == ["alice", "bob"]

    def test_note_is_frozen(self):
        n = Note(content="test", source_id=uuid.uuid4())
        with pytest.raises(ValidationError):
            n.content = "changed"

    def test_unique_uuids(self):
        sid = uuid.uuid4()
        n1 = Note(content="a", source_id=sid)
        n2 = Note(content="b", source_id=sid)
        assert n1.note_id != n2.note_id

    def test_default_timestamp_is_utc(self):
        n = Note(content="test", source_id=uuid.uuid4())
        assert n.created_at.tzinfo is not None


class TestSignal:
    def test_create_signal(self):
        s = Signal(type="new_note", payload={"note_id": "abc"})
        assert s.type == "new_note"
        assert s.payload == {"note_id": "abc"}
        assert s.processed_at is None

    def test_signal_is_frozen(self):
        s = Signal(type="test")
        with pytest.raises(ValidationError):
            s.type = "changed"


class TestAuditEntry:
    def test_create_audit_entry(self):
        eid = uuid.uuid4()
        a = AuditEntry(entity_type="note", entity_id=eid, action="created")
        assert a.entity_type == "note"
        assert a.entity_id == eid
        assert a.before is None
        assert a.after is None
