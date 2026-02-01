"""Ask pipeline — hybrid search, evidence assembly, citation validation.

Per design.md Section 7.2:
  CLI ask → keyword search (FTS) → vector search → retrieve active beliefs
  → assemble evidence pack → synthesize answer → validate citations
  → output answer + evidence IDs
"""

from __future__ import annotations

from dataclasses import dataclass, field

from second_brain.core.models import BeliefStatus, Note, Belief
from second_brain.core.services.beliefs import BeliefService
from second_brain.core.services.edges import EdgeService
from second_brain.core.services.notes import NoteService
from second_brain.storage.sqlite import Database
from second_brain.storage.vector import VectorStore


@dataclass
class EvidencePack:
    """Assembled evidence for answering a question."""
    query: str
    fts_notes: list[Note] = field(default_factory=list)
    vector_notes: list[tuple[Note, float]] = field(default_factory=list)  # (note, score)
    beliefs: list[Belief] = field(default_factory=list)
    all_note_ids: set[str] = field(default_factory=set)

    @property
    def has_evidence(self) -> bool:
        return bool(self.fts_notes or self.vector_notes or self.beliefs)


@dataclass
class Answer:
    """A grounded answer with citations."""
    query: str
    summary: str
    evidence: EvidencePack
    cited_note_ids: list[str] = field(default_factory=list)
    cited_belief_ids: list[str] = field(default_factory=list)


class AskPipeline:
    def __init__(self, db: Database):
        self.db = db
        self.notes = NoteService(db)
        self.beliefs = BeliefService(db)
        self.edges = EdgeService(db)
        self.vectors = VectorStore(db)

    def ask(self, query: str, limit: int = 10) -> Answer:
        """Execute the full ask pipeline."""
        # 1. Keyword search (FTS)
        fts_results = self.notes.search_notes(query, limit=limit)

        # 2. Vector search
        vector_results_raw = self.vectors.search_similar(query, entity_type="note", limit=limit)
        vector_notes = []
        for note_id, score in vector_results_raw:
            note = self.notes.get_note(note_id)
            if note and score > 0.1:  # Minimum relevance threshold
                vector_notes.append((note, score))

        # 3. Collect all relevant note IDs
        all_note_ids = set()
        for n in fts_results:
            all_note_ids.add(n.note_id)
        for n, _ in vector_notes:
            all_note_ids.add(n.note_id)

        # 4. Retrieve beliefs connected to these notes
        beliefs = self._get_connected_beliefs(all_note_ids)

        # 5. Assemble evidence pack
        evidence = EvidencePack(
            query=query,
            fts_notes=fts_results,
            vector_notes=vector_notes,
            beliefs=beliefs,
            all_note_ids=all_note_ids,
        )

        # 6. Synthesize answer (template-based — no LLM required)
        summary = self._synthesize(evidence)

        # 7. Build answer with citations
        cited_note_ids = list(all_note_ids)
        cited_belief_ids = [b.belief_id for b in beliefs]

        return Answer(
            query=query,
            summary=summary,
            evidence=evidence,
            cited_note_ids=cited_note_ids,
            cited_belief_ids=cited_belief_ids,
        )

    def _get_connected_beliefs(self, note_ids: set[str]) -> list[Belief]:
        """Find beliefs connected to any of the given notes via edges."""
        belief_ids = set()
        for note_id in note_ids:
            edges = self.edges.get_edges_from("note", note_id)
            for edge in edges:
                if edge.to_type.value == "belief":
                    belief_ids.add(edge.to_id)

        beliefs = []
        for bid in belief_ids:
            belief = self.beliefs.get_belief(bid)
            if belief and belief.status in (BeliefStatus.ACTIVE, BeliefStatus.PROPOSED, BeliefStatus.CHALLENGED):
                beliefs.append(belief)
        return beliefs

    def _synthesize(self, evidence: EvidencePack) -> str:
        """Generate a text summary from evidence. Template-based, no LLM."""
        if not evidence.has_evidence:
            return "No relevant evidence found in the knowledge base."

        parts = []

        if evidence.beliefs:
            parts.append("Relevant beliefs:")
            for b in evidence.beliefs:
                status_marker = {
                    BeliefStatus.ACTIVE: "[ACTIVE]",
                    BeliefStatus.PROPOSED: "[PROPOSED]",
                    BeliefStatus.CHALLENGED: "[CHALLENGED]",
                }.get(b.status, f"[{b.status.value.upper()}]")
                parts.append(
                    f"  {status_marker} {b.claim_text} "
                    f"(confidence: {b.confidence:.2f}, id: {b.belief_id[:8]})"
                )

        if evidence.fts_notes:
            parts.append(f"\nSupporting notes ({len(evidence.fts_notes)} keyword matches):")
            for note in evidence.fts_notes[:5]:
                snippet = note.content[:120] + ("..." if len(note.content) > 120 else "")
                parts.append(f"  [{note.note_id[:8]}] {snippet}")

        if evidence.vector_notes:
            # Only show vector results not already in FTS
            fts_ids = {n.note_id for n in evidence.fts_notes}
            unique_vector = [(n, s) for n, s in evidence.vector_notes if n.note_id not in fts_ids]
            if unique_vector:
                parts.append(f"\nSemantically similar notes ({len(unique_vector)} matches):")
                for note, score in unique_vector[:5]:
                    snippet = note.content[:120] + ("..." if len(note.content) > 120 else "")
                    parts.append(f"  [{note.note_id[:8]}] (sim: {score:.2f}) {snippet}")

        return "\n".join(parts)
