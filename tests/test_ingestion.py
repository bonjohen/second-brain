"""Tests for IngestionAgent."""

from second_brain.agents.ingestion import IngestionAgent
from second_brain.core.models import ContentType, SourceKind


class TestIngestionAgent:
    def _make_agent(self, note_service, signal_service):
        return IngestionAgent(note_service, signal_service)

    def test_ingest_creates_source_and_note(self, note_service, signal_service):
        agent = self._make_agent(note_service, signal_service)
        source, note = agent.ingest("Hello world")
        assert source is not None
        assert note is not None
        assert note.content == "Hello world"
        assert source.kind == SourceKind.USER

    def test_ingest_extracts_tags(self, note_service, signal_service):
        agent = self._make_agent(note_service, signal_service)
        _, note = agent.ingest("Learning #python and #rust today")
        assert "python" in note.tags
        assert "rust" in note.tags

    def test_ingest_extracts_entities(self, note_service, signal_service):
        agent = self._make_agent(note_service, signal_service)
        _, note = agent.ingest("Meeting with @alice and @bob")
        assert "alice" in note.entities
        assert "bob" in note.entities

    def test_ingest_merges_extra_tags(self, note_service, signal_service):
        agent = self._make_agent(note_service, signal_service)
        _, note = agent.ingest("Learning #python", extra_tags=["tutorial", "beginner"])
        assert "python" in note.tags
        assert "tutorial" in note.tags
        assert "beginner" in note.tags

    def test_ingest_emits_new_note_signal(self, note_service, signal_service):
        agent = self._make_agent(note_service, signal_service)
        _, note = agent.ingest("Test signal emission")

        signals = signal_service.get_unprocessed("new_note")
        assert len(signals) == 1
        assert signals[0].payload["note_id"] == str(note.note_id)

    def test_ingest_with_content_type(self, note_service, signal_service):
        agent = self._make_agent(note_service, signal_service)
        _, note = agent.ingest("# Title\nBody", content_type=ContentType.MARKDOWN)
        assert note.content_type == ContentType.MARKDOWN

    def test_extract_tags_no_tags(self):
        assert IngestionAgent.extract_tags("no tags here") == []

    def test_extract_tags_deduplicates(self):
        tags = IngestionAgent.extract_tags("#python #Python #PYTHON")
        assert tags == ["python"]

    def test_extract_entities_no_entities(self):
        assert IngestionAgent.extract_entities("no entities here") == []

    def test_extract_entities_deduplicates(self):
        entities = IngestionAgent.extract_entities("@Alice @alice @ALICE")
        assert entities == ["alice"]

    def test_extract_tags_truncates_long_tags(self):
        long_tag = "#" + "a" * 200
        tags = IngestionAgent.extract_tags(f"text {long_tag} #short")
        assert tags == ["short"]  # long tag filtered out
