"""SynthesisAgent -- groups notes and proposes beliefs."""

from __future__ import annotations

import uuid
from collections import defaultdict

from second_brain.core.models import EntityType, RelType
from second_brain.core.services.beliefs import BeliefService
from second_brain.core.services.edges import EdgeService
from second_brain.core.services.notes import NoteService
from second_brain.core.services.signals import SignalService


class SynthesisAgent:
    """Processes new_note signals, groups notes by shared tags/entities,
    and creates beliefs for groups with >= 2 notes.

    For each group:
    1. Create a belief with a claim summarizing the group.
    2. Create supports edges from notes to belief.
    3. Emit belief_proposed signal.
    """

    def __init__(
        self,
        note_service: NoteService,
        belief_service: BeliefService,
        edge_service: EdgeService,
        signal_service: SignalService,
    ) -> None:
        self._notes = note_service
        self._beliefs = belief_service
        self._edges = edge_service
        self._signals = signal_service

    def run(self) -> list[uuid.UUID]:
        """Process unprocessed new_note signals and synthesize beliefs.

        Returns list of created belief IDs.
        """
        signals = self._signals.get_unprocessed("new_note")
        if not signals:
            return []

        # Collect note IDs from signals
        note_ids: list[uuid.UUID] = []
        for signal in signals:
            nid = signal.payload.get("note_id")
            if nid:
                note_ids.append(uuid.UUID(nid))
            self._signals.mark_processed(signal.signal_id)

        # Load notes
        notes = []
        for nid in note_ids:
            note = self._notes.get_note(nid)
            if note:
                notes.append(note)

        if not notes:
            return []

        # Group notes by shared tags and entities
        tag_groups: dict[str, list] = defaultdict(list)
        entity_groups: dict[str, list] = defaultdict(list)

        for note in notes:
            for tag in note.tags:
                tag_groups[tag].append(note)
            for entity in note.entities:
                entity_groups[entity].append(note)

        # Also check existing notes for same tags
        all_groups: dict[str, list] = {}
        for tag, tag_notes in tag_groups.items():
            existing = self._notes.list_notes(tag=tag, limit=100)
            merged_ids = {str(n.note_id) for n in tag_notes}
            for en in existing:
                if str(en.note_id) not in merged_ids:
                    tag_notes.append(en)
                    merged_ids.add(str(en.note_id))
            if len(tag_notes) >= 2:
                all_groups[f"tag:{tag}"] = tag_notes

        for entity, entity_notes in entity_groups.items():
            existing = self._notes.list_notes(entity=entity, limit=100)
            merged_ids = {str(n.note_id) for n in entity_notes}
            for en in existing:
                if str(en.note_id) not in merged_ids:
                    entity_notes.append(en)
                    merged_ids.add(str(en.note_id))
            if len(entity_notes) >= 2:
                all_groups[f"entity:{entity}"] = entity_notes

        # Create beliefs for each group
        created: list[uuid.UUID] = []
        for group_key, group_notes in all_groups.items():
            kind, value = group_key.split(":", 1)
            claim = f"Multiple notes discuss {value} ({len(group_notes)} sources)"

            belief = self._beliefs.create_belief(
                claim_text=claim,
                confidence=min(0.3 + 0.1 * len(group_notes), 0.9),
                derived_from_agent="synthesis",
                scope={"group_key": group_key, "note_count": len(group_notes)},
            )

            # Create supports edges from each note to the belief
            for note in group_notes:
                self._edges.create_edge(
                    from_type=EntityType.NOTE,
                    from_id=note.note_id,
                    rel_type=RelType.SUPPORTS,
                    to_type=EntityType.BELIEF,
                    to_id=belief.belief_id,
                )

            self._signals.emit(
                "belief_proposed",
                {"belief_id": str(belief.belief_id), "group_key": group_key},
            )

            created.append(belief.belief_id)

        return created
