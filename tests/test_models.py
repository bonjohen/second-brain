"""Tests for core Pydantic models and enums."""

import uuid

import pytest
from pydantic import ValidationError

from second_brain.core.models import (
    AuditEntry,
    Belief,
    BeliefStatus,
    ContentType,
    DecayModel,
    Edge,
    EntityType,
    Note,
    RelType,
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

    def test_belief_status_values(self):
        assert set(BeliefStatus) == {
            BeliefStatus.PROPOSED,
            BeliefStatus.ACTIVE,
            BeliefStatus.CHALLENGED,
            BeliefStatus.DEPRECATED,
            BeliefStatus.ARCHIVED,
        }

    def test_decay_model_values(self):
        assert set(DecayModel) == {
            DecayModel.EXPONENTIAL,
            DecayModel.NONE,
        }

    def test_entity_type_values(self):
        assert set(EntityType) == {
            EntityType.NOTE,
            EntityType.BELIEF,
            EntityType.SOURCE,
        }

    def test_rel_type_values(self):
        assert set(RelType) == {
            RelType.SUPPORTS,
            RelType.CONTRADICTS,
            RelType.DERIVED_FROM,
            RelType.RELATED_TO,
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

    def test_oversized_content_rejected(self):
        with pytest.raises(ValidationError, match="maximum length"):
            Note(content="x" * 102_401, source_id=uuid.uuid4())

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


class TestBelief:
    def test_create_belief(self):
        b = Belief(claim_text="Python is versatile")
        assert isinstance(b.belief_id, uuid.UUID)
        assert b.claim_text == "Python is versatile"
        assert b.status == BeliefStatus.PROPOSED
        assert b.confidence == 0.5
        assert b.decay_model == DecayModel.EXPONENTIAL

    def test_belief_empty_claim_rejected(self):
        with pytest.raises(ValidationError, match="must not be empty"):
            Belief(claim_text="")

    def test_belief_whitespace_claim_rejected(self):
        with pytest.raises(ValidationError, match="must not be empty"):
            Belief(claim_text="   \n  ")

    def test_belief_confidence_bounds(self):
        with pytest.raises(ValidationError):
            Belief(claim_text="test", confidence=1.5)
        with pytest.raises(ValidationError):
            Belief(claim_text="test", confidence=-0.1)

    def test_belief_is_frozen(self):
        b = Belief(claim_text="test")
        with pytest.raises(ValidationError):
            b.claim_text = "changed"


class TestEdge:
    def test_create_edge(self):
        nid = uuid.uuid4()
        bid = uuid.uuid4()
        e = Edge(
            from_type=EntityType.NOTE,
            from_id=nid,
            rel_type=RelType.SUPPORTS,
            to_type=EntityType.BELIEF,
            to_id=bid,
        )
        assert e.from_type == EntityType.NOTE
        assert e.rel_type == RelType.SUPPORTS

    def test_edge_is_frozen(self):
        e = Edge(
            from_type=EntityType.NOTE,
            from_id=uuid.uuid4(),
            rel_type=RelType.SUPPORTS,
            to_type=EntityType.BELIEF,
            to_id=uuid.uuid4(),
        )
        with pytest.raises(ValidationError):
            e.rel_type = RelType.CONTRADICTS


class TestAuditEntry:
    def test_create_audit_entry(self):
        eid = uuid.uuid4()
        a = AuditEntry(entity_type="note", entity_id=eid, action="created")
        assert a.entity_type == "note"
        assert a.entity_id == eid
        assert a.before is None
        assert a.after is None
