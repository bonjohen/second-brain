"""CuratorAgent -- archives cold items, deduplicates, and distills summaries."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime, timedelta

from second_brain.core.models import BeliefStatus, EntityType, RelType
from second_brain.core.services.audit import AuditService
from second_brain.core.services.beliefs import BeliefService
from second_brain.core.services.edges import EdgeService
from second_brain.core.services.notes import NoteService
from second_brain.core.services.signals import SignalService
from second_brain.core.utils import parse_utc_datetime

logger = logging.getLogger(__name__)

DEFAULT_COLD_DAYS = 90
DEFAULT_SIMILARITY_THRESHOLD = 0.95


class CuratorAgent:
    """Maintains system health: archives cold items, deduplicates, distills summaries.

    All actions are logged to the audit trail. No silent deletion.
    Archived items remain in the database and are queryable.
    """

    def __init__(
        self,
        note_service: NoteService,
        belief_service: BeliefService,
        edge_service: EdgeService,
        signal_service: SignalService,
        audit_service: AuditService,
        vector_store=None,
        cold_days: int = DEFAULT_COLD_DAYS,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> None:
        self._notes = note_service
        self._beliefs = belief_service
        self._edges = edge_service
        self._signals = signal_service
        self._audit = audit_service
        self._vector_store = vector_store
        self._cold_days = cold_days
        self._similarity_threshold = similarity_threshold

    def run(self) -> dict[str, int]:
        """Run all curator tasks. Returns counts of actions taken."""
        archived = self.archive_cold_beliefs()
        duplicates = self.deduplicate_beliefs()
        distilled = self.distill_notes()
        return {
            "archived": archived,
            "deduplicated": duplicates,
            "distilled": distilled,
        }

    def archive_cold_beliefs(self, now: datetime | None = None) -> int:
        """Archive deprecated beliefs not updated in cold_days. Returns count archived."""
        if now is None:
            now = datetime.now(UTC)

        cutoff = now - timedelta(days=self._cold_days)
        count = 0

        deprecated = self._beliefs.list_beliefs(
            status_filter=BeliefStatus.DEPRECATED, limit=1000
        )
        for belief in deprecated:
            updated_at = parse_utc_datetime(belief.updated_at)

            if updated_at < cutoff:
                try:
                    self._beliefs.update_belief_status(
                        belief.belief_id, BeliefStatus.ARCHIVED
                    )
                    count += 1
                except ValueError:
                    logger.warning(
                        "Skipping archive for belief %s: invalid state transition",
                        belief.belief_id,
                    )

        return count

    def deduplicate_beliefs(
        self, max_beliefs: int = 200, time_budget: float = 30.0
    ) -> int:
        """Find and merge near-duplicate beliefs. Returns count of merges.

        Args:
            max_beliefs: Maximum number of beliefs to consider (caps O(n^2)).
            time_budget: Maximum seconds to spend on pairwise comparisons.
        """
        if self._vector_store is None:
            return 0

        active_beliefs = self._beliefs.list_beliefs(
            status_filter=BeliefStatus.ACTIVE, limit=1000
        )
        proposed_beliefs = self._beliefs.list_beliefs(
            status_filter=BeliefStatus.PROPOSED, limit=1000
        )
        all_beliefs = active_beliefs + proposed_beliefs

        if len(all_beliefs) > max_beliefs:
            logger.warning(
                "Truncating dedup from %d to %d beliefs", len(all_beliefs), max_beliefs
            )
            all_beliefs = all_beliefs[:max_beliefs]

        if len(all_beliefs) < 2:
            return 0

        # Compute embeddings for all beliefs
        embeddings: list[tuple[uuid.UUID, object]] = []
        for belief in all_beliefs:
            emb = self._vector_store.compute_embedding(belief.claim_text)
            embeddings.append((belief.belief_id, emb))

        merged_ids: set[str] = set()
        merge_count = 0
        deadline = time.monotonic() + time_budget

        for i in range(len(embeddings)):
            bid_i = embeddings[i][0]
            if str(bid_i) in merged_ids:
                continue
            for j in range(i + 1, len(embeddings)):
                if time.monotonic() > deadline:
                    logger.warning(
                        "Dedup time budget (%.0fs) exceeded after %d merges",
                        time_budget,
                        merge_count,
                    )
                    return merge_count
                bid_j = embeddings[j][0]
                if str(bid_j) in merged_ids:
                    continue

                sim = self._vector_store.cosine_similarity(
                    embeddings[i][1], embeddings[j][1]
                )
                if sim >= self._similarity_threshold:
                    # Merge: keep the first, deprecate the second
                    # Transfer edges from j to i
                    edges_j = self._edges.get_edges(EntityType.BELIEF, bid_j)
                    for edge in edges_j:
                        if edge.to_id == bid_j:
                            self._edges.create_edge(
                                edge.from_type, edge.from_id,
                                edge.rel_type, EntityType.BELIEF, bid_i,
                            )
                        elif edge.from_id == bid_j:
                            self._edges.create_edge(
                                EntityType.BELIEF, bid_i,
                                edge.rel_type, edge.to_type, edge.to_id,
                            )
                        self._edges.delete_edge(edge.edge_id)

                    # Deprecate the duplicate
                    belief_j = self._beliefs.get_belief(bid_j)
                    try:
                        if belief_j and belief_j.status in (
                            BeliefStatus.PROPOSED, BeliefStatus.ACTIVE
                        ):
                            if belief_j.status == BeliefStatus.PROPOSED:
                                self._beliefs.update_belief_status(
                                    bid_j, BeliefStatus.ACTIVE
                                )
                            self._beliefs.update_belief_status(
                                bid_j, BeliefStatus.CHALLENGED
                            )
                            self._beliefs.update_belief_status(
                                bid_j, BeliefStatus.DEPRECATED
                            )
                    except ValueError:
                        logger.warning(
                            "Skipping deprecation for belief %s: invalid state transition",
                            bid_j,
                        )

                    # Create related_to edge between kept and merged
                    self._edges.create_edge(
                        EntityType.BELIEF, bid_i,
                        RelType.RELATED_TO,
                        EntityType.BELIEF, bid_j,
                    )

                    self._audit.log_event(
                        entity_type="belief",
                        entity_id=bid_j,
                        action="deduplicated",
                        before={"merged_into": str(bid_i)},
                    )

                    merged_ids.add(str(bid_j))
                    merge_count += 1

        return merge_count

    def distill_notes(self) -> int:
        """Create summary notes from clusters of related notes. Returns count of summaries."""
        # Paginate to collect all notes
        all_notes: list = []
        offset = 0
        batch_size = 1000
        while True:
            batch = self._notes.list_notes(limit=batch_size, offset=offset)
            if not batch:
                break
            all_notes.extend(batch)
            offset += batch_size

        # Group notes by tags -- find tags with 5+ notes
        tag_groups: dict[str, list] = {}
        for note in all_notes:
            for tag in note.tags:
                tag_groups.setdefault(tag, []).append(note)

        distill_count = 0
        for tag, notes in tag_groups.items():
            if len(notes) < 5:
                continue

            # Check if a distillation already exists for this tag
            existing = self._notes.list_notes(tag=f"distill-{tag}", limit=1)
            if existing:
                continue

            # Create a summary note
            snippets = []
            for note in notes[:10]:  # Cap at 10 notes
                first_line = note.content.split("\n")[0][:80]
                snippets.append(f"- {first_line}")

            summary = (
                f"Summary of {len(notes)} notes about '{tag}':\n"
                + "\n".join(snippets)
            )

            source = self._notes.create_source(kind="user", locator="curator:distill")
            summary_note = self._notes.create_note(
                content=summary,
                content_type="text",
                source_id=source.source_id,
                tags=[f"distill-{tag}", tag, "summary"],
            )

            # Create edges from source notes to summary
            for note in notes[:10]:
                self._edges.create_edge(
                    EntityType.NOTE, note.note_id,
                    RelType.DERIVED_FROM,
                    EntityType.NOTE, summary_note.note_id,
                )

            self._signals.emit(
                "note_distilled",
                {"note_id": str(summary_note.note_id), "tag": tag},
            )

            distill_count += 1

        return distill_count
