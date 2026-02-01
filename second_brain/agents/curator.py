"""CuratorAgent — archive, merge, and distillation per design.md Section 5.4.

Input: scheduled run
Output: archive, merge, distillation

Rules:
  - Cold if not referenced in N days → archive candidate
  - Duplicate if cosine similarity ≥ threshold → merge candidate

Actions:
  - Archive with grace period
  - Merge notes/beliefs
  - Create summary notes
  - No silent deletion
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from second_brain.core.models import BeliefStatus, EdgeFromType, EdgeRelType, EdgeToType
from second_brain.core.services.audit import AuditService
from second_brain.core.services.beliefs import BeliefService
from second_brain.core.services.edges import EdgeService
from second_brain.core.services.notes import NoteService
from second_brain.core.services.signals import SignalService
from second_brain.storage.sqlite import Database
from second_brain.storage.vector import VectorStore, _cosine_similarity

# Policy constants
COLD_DAYS = 90  # Days without reference before archival candidate
SIMILARITY_THRESHOLD = 0.92  # Cosine similarity for duplicate detection
GRACE_PERIOD_DAYS = 7  # Days before archival is finalized


class CuratorAgent:
    def __init__(self, db: Database):
        self.db = db
        self.notes = NoteService(db)
        self.beliefs = BeliefService(db)
        self.edges = EdgeService(db)
        self.audit = AuditService(db)
        self.signals = SignalService(db)
        self.vectors = VectorStore(db)

    def run(self) -> list[dict]:
        """Run full curation cycle."""
        results = []

        # 1. Archive cold beliefs (deprecated → archived)
        results.extend(self._archive_cold_beliefs())

        # 2. Detect and flag duplicate beliefs
        results.extend(self._detect_duplicate_beliefs())

        # 3. Archive stale deprecated beliefs
        results.extend(self._archive_deprecated())

        return results

    def _archive_cold_beliefs(self) -> list[dict]:
        """Archive beliefs that haven't been referenced in COLD_DAYS."""
        results = []
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=COLD_DAYS)

        deprecated = self.beliefs.list_beliefs(status=BeliefStatus.DEPRECATED, limit=500)
        for belief in deprecated:
            updated = datetime.fromisoformat(str(belief.updated_at))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)

            if updated < cutoff:
                self.beliefs.transition(belief.belief_id, BeliefStatus.ARCHIVED)
                self.audit.log(
                    "belief", belief.belief_id, "curator_archive",
                    old_value={"status": "deprecated"},
                    new_value={"status": "archived", "reason": "cold"},
                )
                results.append({
                    "action": "archive",
                    "belief_id": belief.belief_id,
                    "reason": "cold",
                })

        return results

    def _detect_duplicate_beliefs(self) -> list[dict]:
        """Find beliefs with very similar claim text and link them."""
        results = []
        active_beliefs = self.beliefs.list_beliefs(status=BeliefStatus.ACTIVE, limit=500)
        proposed_beliefs = self.beliefs.list_beliefs(status=BeliefStatus.PROPOSED, limit=500)
        all_beliefs = active_beliefs + proposed_beliefs

        # Compute embeddings for all beliefs
        for b in all_beliefs:
            self.vectors.store_embedding(b.belief_id, "belief", b.claim_text)

        # Pairwise comparison
        for i, b1 in enumerate(all_beliefs):
            vec1 = self.vectors.get_embedding(b1.belief_id)
            if vec1 is None:
                continue
            for b2 in all_beliefs[i + 1:]:
                vec2 = self.vectors.get_embedding(b2.belief_id)
                if vec2 is None:
                    continue
                sim = _cosine_similarity(vec1, vec2)
                if sim >= SIMILARITY_THRESHOLD:
                    # Check if already linked
                    existing = self.edges.get_edges_from("belief", b1.belief_id, "related")
                    already_linked = any(e.to_id == b2.belief_id for e in existing)
                    if not already_linked:
                        self.edges.create_edge(
                            from_type=EdgeFromType.BELIEF,
                            from_id=b1.belief_id,
                            rel_type=EdgeRelType.RELATED,
                            to_type=EdgeToType.BELIEF,
                            to_id=b2.belief_id,
                        )
                        results.append({
                            "action": "duplicate_detected",
                            "belief_a": b1.belief_id,
                            "belief_b": b2.belief_id,
                            "similarity": sim,
                        })

        return results

    def _archive_deprecated(self) -> list[dict]:
        """Archive deprecated beliefs past grace period."""
        results = []
        now = datetime.now(timezone.utc)
        grace_cutoff = now - timedelta(days=GRACE_PERIOD_DAYS)

        deprecated = self.beliefs.list_beliefs(status=BeliefStatus.DEPRECATED, limit=500)
        for belief in deprecated:
            updated = datetime.fromisoformat(str(belief.updated_at))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)

            if updated < grace_cutoff:
                self.beliefs.transition(belief.belief_id, BeliefStatus.ARCHIVED)
                self.audit.log(
                    "belief", belief.belief_id, "curator_archive",
                    old_value={"status": "deprecated"},
                    new_value={"status": "archived", "reason": "grace_period_expired"},
                )
                results.append({
                    "action": "archive",
                    "belief_id": belief.belief_id,
                    "reason": "grace_period_expired",
                })

        return results
