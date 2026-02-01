"""Phase 1 tests — beliefs, edges, confidence, contradictions, ask pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from second_brain.agents.challenger import ChallengerAgent
from second_brain.agents.ingestion import IngestionAgent
from second_brain.agents.synthesis import SynthesisAgent
from second_brain.core.models import (
    BeliefStatus, DecayModel, EdgeFromType, EdgeRelType, EdgeToType,
)
from second_brain.core.rules.confidence import compute_confidence, ACTIVATION_THRESHOLD
from second_brain.core.rules.contradictions import detect_contradiction
from second_brain.core.rules.decay import compute_decay
from second_brain.core.services.ask import AskPipeline
from second_brain.core.services.beliefs import BeliefService, InvalidTransitionError
from second_brain.core.services.edges import EdgeService
from second_brain.core.services.notes import NoteService
from second_brain.storage.migrations.runner import ensure_schema
from second_brain.storage.sqlite import Database
from second_brain.storage.vector import VectorStore


@pytest.fixture
def db(tmp_path):
    db = Database(tmp_path / "test.db")
    ensure_schema(db)
    yield db
    db.close()


# ── Edge service ─────────────────────────────────────────────────────────────


class TestEdgeService:
    def test_create_edge(self, db):
        notes = NoteService(db)
        beliefs = BeliefService(db)

        source = notes.create_source()
        note = notes.create_note(content="test", source_id=source.source_id)
        belief = beliefs.create_belief(claim_text="test claim")

        edges = EdgeService(db)
        edge = edges.create_edge(
            from_type=EdgeFromType.NOTE,
            from_id=note.note_id,
            rel_type=EdgeRelType.SUPPORTS,
            to_type=EdgeToType.BELIEF,
            to_id=belief.belief_id,
        )
        assert edge.edge_id

    def test_referential_integrity(self, db):
        edges = EdgeService(db)
        with pytest.raises(ValueError, match="does not exist"):
            edges.create_edge(
                from_type=EdgeFromType.NOTE,
                from_id="nonexistent",
                rel_type=EdgeRelType.SUPPORTS,
                to_type=EdgeToType.BELIEF,
                to_id="also-nonexistent",
            )

    def test_get_edges_from_to(self, db):
        notes = NoteService(db)
        beliefs = BeliefService(db)
        edges = EdgeService(db)

        source = notes.create_source()
        n1 = notes.create_note(content="note 1", source_id=source.source_id)
        n2 = notes.create_note(content="note 2", source_id=source.source_id)
        b = beliefs.create_belief(claim_text="claim")

        edges.create_edge(EdgeFromType.NOTE, n1.note_id, EdgeRelType.SUPPORTS, EdgeToType.BELIEF, b.belief_id)
        edges.create_edge(EdgeFromType.NOTE, n2.note_id, EdgeRelType.SUPPORTS, EdgeToType.BELIEF, b.belief_id)

        support = edges.get_support_edges(b.belief_id)
        assert len(support) == 2


# ── Belief lifecycle ─────────────────────────────────────────────────────────


class TestBeliefLifecycle:
    def test_create_proposed(self, db):
        svc = BeliefService(db)
        b = svc.create_belief(claim_text="Python is popular")
        assert b.status == BeliefStatus.PROPOSED

    def test_valid_transitions(self, db):
        svc = BeliefService(db)
        b = svc.create_belief(claim_text="test")

        b = svc.transition(b.belief_id, BeliefStatus.ACTIVE)
        assert b.status == BeliefStatus.ACTIVE

        b = svc.transition(b.belief_id, BeliefStatus.CHALLENGED)
        assert b.status == BeliefStatus.CHALLENGED

        b = svc.transition(b.belief_id, BeliefStatus.DEPRECATED)
        assert b.status == BeliefStatus.DEPRECATED

        b = svc.transition(b.belief_id, BeliefStatus.ARCHIVED)
        assert b.status == BeliefStatus.ARCHIVED

    def test_invalid_transition(self, db):
        svc = BeliefService(db)
        b = svc.create_belief(claim_text="test")
        with pytest.raises(InvalidTransitionError):
            svc.transition(b.belief_id, BeliefStatus.DEPRECATED)

    def test_challenged_can_return_to_active(self, db):
        svc = BeliefService(db)
        b = svc.create_belief(claim_text="test")
        svc.transition(b.belief_id, BeliefStatus.ACTIVE)
        svc.transition(b.belief_id, BeliefStatus.CHALLENGED)
        b = svc.transition(b.belief_id, BeliefStatus.ACTIVE)
        assert b.status == BeliefStatus.ACTIVE

    def test_update_confidence(self, db):
        svc = BeliefService(db)
        b = svc.create_belief(claim_text="test", confidence=0.5)
        b = svc.update_confidence(b.belief_id, 0.8)
        assert b.confidence == 0.8

    def test_confidence_clamped(self, db):
        svc = BeliefService(db)
        b = svc.create_belief(claim_text="test")
        b = svc.update_confidence(b.belief_id, 1.5)
        assert b.confidence == 1.0
        b = svc.update_confidence(b.belief_id, -0.5)
        assert b.confidence == 0.0


# ── Confidence rules ─────────────────────────────────────────────────────────


class TestConfidenceRules:
    def test_basic_confidence(self, db):
        notes = NoteService(db)
        beliefs = BeliefService(db)
        edges = EdgeService(db)

        source = notes.create_source()
        n1 = notes.create_note(content="support 1", source_id=source.source_id)
        n2 = notes.create_note(content="support 2", source_id=source.source_id)
        b = beliefs.create_belief(claim_text="test")

        edges.create_edge(EdgeFromType.NOTE, n1.note_id, EdgeRelType.SUPPORTS, EdgeToType.BELIEF, b.belief_id)
        edges.create_edge(EdgeFromType.NOTE, n2.note_id, EdgeRelType.SUPPORTS, EdgeToType.BELIEF, b.belief_id)

        conf = compute_confidence(db, b.belief_id, b.updated_at.isoformat())
        assert conf > 0.0

    def test_contradiction_reduces_confidence(self, db):
        notes = NoteService(db)
        beliefs = BeliefService(db)
        edges = EdgeService(db)

        source = notes.create_source()
        n_support = notes.create_note(content="support", source_id=source.source_id)
        n_contra = notes.create_note(content="counter", source_id=source.source_id)
        b = beliefs.create_belief(claim_text="test")

        edges.create_edge(EdgeFromType.NOTE, n_support.note_id, EdgeRelType.SUPPORTS, EdgeToType.BELIEF, b.belief_id)
        conf_before = compute_confidence(db, b.belief_id, b.updated_at.isoformat())

        edges.create_edge(EdgeFromType.NOTE, n_contra.note_id, EdgeRelType.CONTRADICTS, EdgeToType.BELIEF, b.belief_id)
        conf_after = compute_confidence(db, b.belief_id, b.updated_at.isoformat())

        assert conf_after < conf_before


# ── Decay rules ──────────────────────────────────────────────────────────────


class TestDecayRules:
    def test_no_decay(self):
        factor = compute_decay("2020-01-01T00:00:00+00:00", "none")
        assert factor == 1.0

    def test_recent_minimal_decay(self):
        now = datetime.now(timezone.utc)
        factor = compute_decay(now.isoformat(), "exponential", now=now)
        assert factor == 1.0

    def test_half_life(self):
        now = datetime.now(timezone.utc)
        thirty_days_ago = (now - timedelta(days=30)).isoformat()
        factor = compute_decay(thirty_days_ago, "exponential", half_life_days=30, now=now)
        assert abs(factor - 0.5) < 0.01

    def test_old_content_decays(self):
        now = datetime.now(timezone.utc)
        year_ago = (now - timedelta(days=365)).isoformat()
        factor = compute_decay(year_ago, "exponential", now=now)
        assert factor < 0.01


# ── Contradiction rules ──────────────────────────────────────────────────────


class TestContradictions:
    def test_exact_negation(self):
        assert detect_contradiction("Python is fast", "not Python is fast")
        assert detect_contradiction("Python is fast", "it is not true that Python is fast")

    def test_opposing_predicate(self):
        assert detect_contradiction("Python is fast", "Python is not fast")

    def test_no_contradiction(self):
        assert not detect_contradiction("Python is fast", "Java is slow")
        assert not detect_contradiction("Apples are red", "Bananas are yellow")

    def test_case_insensitive(self):
        assert detect_contradiction("python is fast", "Python Is Not Fast")


# ── Vector storage ───────────────────────────────────────────────────────────


class TestVectorStore:
    def test_store_and_search(self, db):
        vs = VectorStore(db)
        notes = NoteService(db)
        source = notes.create_source()
        n = notes.create_note(content="machine learning algorithms", source_id=source.source_id)

        vs.store_embedding(n.note_id, "note", n.content)
        results = vs.search_similar("deep learning", entity_type="note")
        assert len(results) > 0
        assert results[0][0] == n.note_id

    def test_rebuild(self, db):
        vs = VectorStore(db)
        notes = NoteService(db)
        source = notes.create_source()
        n1 = notes.create_note(content="first note", source_id=source.source_id)
        n2 = notes.create_note(content="second note", source_id=source.source_id)

        count = vs.rebuild_all([(n1.note_id, n1.content), (n2.note_id, n2.content)])
        assert count == 2


# ── Synthesis agent ──────────────────────────────────────────────────────────


class TestSynthesisAgent:
    def test_generates_beliefs(self, db):
        ingestion = IngestionAgent(db)
        ingestion.ingest("Research on #AI shows neural networks are effective")
        ingestion.ingest("New #AI breakthrough in language models")

        synthesis = SynthesisAgent(db)
        results = synthesis.run()
        assert len(results) > 0
        assert results[0]["belief_id"]

    def test_no_duplicates(self, db):
        ingestion = IngestionAgent(db)
        ingestion.ingest("#Python is versatile")
        ingestion.ingest("#Python has great libraries")

        synthesis = SynthesisAgent(db)
        r1 = synthesis.run()
        r2 = synthesis.run()
        assert len(r2) == 0  # No new beliefs created


# ── Challenger agent ─────────────────────────────────────────────────────────


class TestChallengerAgent:
    def test_detects_contradicting_beliefs(self, db):
        beliefs = BeliefService(db)
        b1 = beliefs.create_belief(claim_text="Python is fast")
        beliefs.transition(b1.belief_id, BeliefStatus.ACTIVE)
        b2 = beliefs.create_belief(claim_text="Python is not fast")
        beliefs.transition(b2.belief_id, BeliefStatus.ACTIVE)

        challenger = ChallengerAgent(db)
        results = challenger.run()
        assert len(results) > 0


# ── Ask pipeline ─────────────────────────────────────────────────────────────


class TestAskPipeline:
    def test_basic_ask(self, db):
        ingestion = IngestionAgent(db)
        ingestion.ingest("Python was created by Guido van Rossum in 1991")
        ingestion.ingest("Python is widely used in data science and machine learning")

        pipeline = AskPipeline(db)
        answer = pipeline.ask("Python")
        assert answer.evidence.has_evidence
        assert len(answer.cited_note_ids) > 0

    def test_no_results(self, db):
        pipeline = AskPipeline(db)
        answer = pipeline.ask("quantum_physics_xyz")
        assert not answer.evidence.has_evidence
