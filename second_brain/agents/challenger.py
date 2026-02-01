"""ChallengerAgent — contradiction detection per design.md Section 5.3.

Input: signal:belief_proposed, signal:new_note
Output: state changes, contradiction edges

Rules:
  - Exact negation detection
  - Same-subject opposing predicates
  - Confidence drop if contradiction exists

Actions:
  - Add contradicts edge
  - Set belief → challenged
  - Emit signal:belief_challenged
"""

from __future__ import annotations

from second_brain.core.models import BeliefStatus, EdgeFromType, EdgeRelType, EdgeToType
from second_brain.core.rules.confidence import compute_confidence
from second_brain.core.rules.contradictions import detect_contradiction
from second_brain.core.services.beliefs import BeliefService
from second_brain.core.services.edges import EdgeService
from second_brain.core.services.notes import NoteService
from second_brain.core.services.signals import SignalService
from second_brain.storage.sqlite import Database


class ChallengerAgent:
    def __init__(self, db: Database):
        self.db = db
        self.beliefs = BeliefService(db)
        self.edges = EdgeService(db)
        self.notes = NoteService(db)
        self.signals = SignalService(db)

    def run(self) -> list[dict]:
        """Check all active/proposed beliefs for contradictions against each other."""
        results = []

        beliefs = self.beliefs.list_beliefs(limit=1000)
        active_beliefs = [
            b for b in beliefs
            if b.status in (BeliefStatus.PROPOSED, BeliefStatus.ACTIVE)
        ]

        # Check each pair of beliefs for contradiction
        for i, b1 in enumerate(active_beliefs):
            for b2 in active_beliefs[i + 1:]:
                if detect_contradiction(b1.claim_text, b2.claim_text):
                    result = self._handle_contradiction(b1, b2)
                    if result:
                        results.append(result)

        # Also check beliefs against note content
        notes = self.notes.list_notes(limit=500)
        for belief in active_beliefs:
            for note in notes:
                if detect_contradiction(belief.claim_text, note.content):
                    result = self._handle_note_contradiction(belief, note)
                    if result:
                        results.append(result)

        return results

    def _handle_contradiction(self, b1, b2) -> dict | None:
        """Create contradiction edge between two beliefs and challenge them."""
        # Check if edge already exists
        existing = self.edges.get_edges_from("belief", b1.belief_id, "contradicts")
        for e in existing:
            if e.to_id == b2.belief_id:
                return None  # Already recorded

        # Create bidirectional contradiction edges
        self.edges.create_edge(
            from_type=EdgeFromType.BELIEF,
            from_id=b1.belief_id,
            rel_type=EdgeRelType.CONTRADICTS,
            to_type=EdgeToType.BELIEF,
            to_id=b2.belief_id,
        )

        # Challenge both beliefs
        challenged = []
        for b in [b1, b2]:
            if b.status == BeliefStatus.ACTIVE:
                self.beliefs.transition(b.belief_id, BeliefStatus.CHALLENGED)
                challenged.append(b.belief_id)
            elif b.status == BeliefStatus.PROPOSED:
                # Can't directly challenge a proposed belief; update confidence instead
                new_conf = compute_confidence(
                    self.db, b.belief_id, b.updated_at.isoformat(), b.decay_model.value
                )
                self.beliefs.update_confidence(b.belief_id, new_conf)

        self.signals.emit(
            "belief_challenged",
            {"belief_ids": [b1.belief_id, b2.belief_id], "type": "belief_vs_belief"},
        )

        return {
            "type": "belief_contradiction",
            "belief_a": b1.belief_id,
            "belief_b": b2.belief_id,
            "challenged": challenged,
        }

    def _handle_note_contradiction(self, belief, note) -> dict | None:
        """Handle a note that contradicts a belief."""
        # Check if edge already exists
        existing = self.edges.get_edges_from("note", note.note_id, "contradicts")
        for e in existing:
            if e.to_id == belief.belief_id:
                return None

        self.edges.create_edge(
            from_type=EdgeFromType.NOTE,
            from_id=note.note_id,
            rel_type=EdgeRelType.CONTRADICTS,
            to_type=EdgeToType.BELIEF,
            to_id=belief.belief_id,
        )

        # Recompute confidence
        new_conf = compute_confidence(
            self.db, belief.belief_id, belief.updated_at.isoformat(), belief.decay_model.value
        )
        self.beliefs.update_confidence(belief.belief_id, new_conf)

        # Challenge if active
        if belief.status == BeliefStatus.ACTIVE:
            self.beliefs.transition(belief.belief_id, BeliefStatus.CHALLENGED)

        self.signals.emit(
            "belief_challenged",
            {"belief_id": belief.belief_id, "note_id": note.note_id, "type": "note_vs_belief"},
        )

        return {
            "type": "note_contradiction",
            "belief_id": belief.belief_id,
            "note_id": note.note_id,
            "new_confidence": new_conf,
        }

    def process_signals(self) -> list[dict]:
        """Process pending belief_proposed and new_note signals."""
        results = []

        for sig_type in ["belief_proposed", "new_note"]:
            pending = self.signals.consume_pending(sig_type)
            for sig in pending:
                self.signals.mark_processed(sig.signal_id)

        # Run full check after processing signals
        if True:  # Always run
            results = self.run()

        return results
