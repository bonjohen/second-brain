"""Tests for AuditService."""

import uuid


class TestAuditService:
    def test_log_event_returns_entry(self, audit_service):
        entity_id = uuid.uuid4()
        entry = audit_service.log_event("note", entity_id, "created", after={"content": "hello"})
        assert entry.entity_type == "note"
        assert entry.entity_id == entity_id
        assert entry.action == "created"
        assert entry.after == {"content": "hello"}
        assert entry.before is None

    def test_get_history_returns_entries_in_order(self, audit_service):
        entity_id = uuid.uuid4()
        audit_service.log_event("note", entity_id, "created")
        audit_service.log_event("note", entity_id, "updated")
        audit_service.log_event("note", entity_id, "archived")

        history = audit_service.get_history("note", entity_id)
        assert len(history) == 3
        assert [e.action for e in history] == ["created", "updated", "archived"]

    def test_get_history_empty_for_unknown_entity(self, audit_service):
        history = audit_service.get_history("note", uuid.uuid4())
        assert history == []

    def test_before_and_after_json_roundtrip(self, audit_service):
        entity_id = uuid.uuid4()
        before = {"status": "active", "confidence": 0.8}
        after = {"status": "challenged", "confidence": 0.3}
        audit_service.log_event("belief", entity_id, "challenged", before=before, after=after)

        history = audit_service.get_history("belief", entity_id)
        assert len(history) == 1
        assert history[0].before == before
        assert history[0].after == after
