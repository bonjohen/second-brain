"""SynthesisAgent — derives beliefs from notes per design.md Section 5.2.

Input: signal:new_note, scheduled run
Output: proposed Beliefs

Steps:
1. Group notes by shared tags/entities
2. Generate belief candidates
3. Create Belief with status=proposed
4. Create supports edges
5. Emit signal:belief_proposed
"""

from __future__ import annotations

import json

from second_brain.core.models import BeliefStatus, DecayModel, EdgeFromType, EdgeRelType, EdgeToType
from second_brain.core.services.beliefs import BeliefService
from second_brain.core.services.edges import EdgeService
from second_brain.core.services.notes import NoteService
from second_brain.core.services.signals import SignalService
from second_brain.storage.sqlite import Database


class SynthesisAgent:
    def __init__(self, db: Database):
        self.db = db
        self.notes = NoteService(db)
        self.beliefs = BeliefService(db)
        self.edges = EdgeService(db)
        self.signals = SignalService(db)

    def run(self, note_ids: list[str] | None = None) -> list[dict]:
        """Run synthesis on given notes, or all recent notes if not specified.

        Returns list of dicts with belief_id and supporting note_ids.
        """
        if note_ids:
            notes = [self.notes.get_note(nid) for nid in note_ids]
            notes = [n for n in notes if n is not None]
        else:
            notes = self.notes.list_notes(limit=200)

        if not notes:
            return []

        # Group notes by shared tags
        tag_groups: dict[str, list] = {}
        for note in notes:
            for tag in note.tags:
                tag_groups.setdefault(tag, []).append(note)

        # Group notes by shared entities
        entity_groups: dict[str, list] = {}
        for note in notes:
            for entity in note.entities:
                entity_groups.setdefault(entity, []).append(note)

        results = []

        # Generate beliefs from tag groups (need at least 2 notes)
        for tag, group_notes in tag_groups.items():
            if len(group_notes) < 2:
                continue

            # Template-based belief generation
            claim = f"Multiple notes reference '{tag}', suggesting it is a significant topic"
            belief = self._create_belief_with_edges(claim, group_notes, f"tag:{tag}")
            if belief:
                results.append(belief)

        # Generate beliefs from entity groups (need at least 2 notes)
        for entity, group_notes in entity_groups.items():
            if len(group_notes) < 2:
                continue

            claim = f"'{entity}' appears across multiple notes as a recurring subject"
            belief = self._create_belief_with_edges(claim, group_notes, f"entity:{entity}")
            if belief:
                results.append(belief)

        return results

    def _create_belief_with_edges(
        self, claim: str, supporting_notes: list, scope_key: str
    ) -> dict | None:
        """Create a belief and link supporting notes via edges."""
        # Check for duplicate claims
        existing = self.beliefs.list_beliefs(limit=1000)
        for b in existing:
            if b.claim_text == claim:
                return None  # Already exists

        belief = self.beliefs.create_belief(
            claim_text=claim,
            confidence=0.5,
            derived_from_agent="synthesis",
            scope={"group": scope_key},
        )

        note_ids = []
        for note in supporting_notes:
            self.edges.create_edge(
                from_type=EdgeFromType.NOTE,
                from_id=note.note_id,
                rel_type=EdgeRelType.SUPPORTS,
                to_type=EdgeToType.BELIEF,
                to_id=belief.belief_id,
            )
            note_ids.append(note.note_id)

        self.signals.emit(
            "belief_proposed",
            {"belief_id": belief.belief_id, "note_ids": note_ids},
        )

        return {
            "belief_id": belief.belief_id,
            "claim": claim,
            "supporting_note_ids": note_ids,
        }

    def process_signals(self) -> list[dict]:
        """Process pending new_note signals."""
        pending = self.signals.consume_pending("new_note")
        note_ids = []
        for sig in pending:
            note_ids.append(sig.payload.get("note_id"))
            self.signals.mark_processed(sig.signal_id)

        if note_ids:
            return self.run(note_ids)
        return []
