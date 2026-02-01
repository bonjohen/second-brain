"""Belief service — full lifecycle management with transition validation.

Status machine per design.md Section 3.2 and 6.2:
  proposed → active     (confidence ≥ threshold AND no contradiction)
  active → challenged   (contradiction exists)
  challenged → active   (contradiction resolved)
  challenged → deprecated (counterevidence dominates)
  deprecated → archived (curator policy)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from second_brain.core.models import Belief, BeliefStatus, DecayModel
from second_brain.core.services.audit import AuditService
from second_brain.storage.sqlite import Database

# Valid state transitions
_VALID_TRANSITIONS: dict[BeliefStatus, set[BeliefStatus]] = {
    BeliefStatus.PROPOSED: {BeliefStatus.ACTIVE},
    BeliefStatus.ACTIVE: {BeliefStatus.CHALLENGED},
    BeliefStatus.CHALLENGED: {BeliefStatus.ACTIVE, BeliefStatus.DEPRECATED},
    BeliefStatus.DEPRECATED: {BeliefStatus.ARCHIVED},
    BeliefStatus.ARCHIVED: set(),
}


class InvalidTransitionError(Exception):
    pass


class BeliefService:
    def __init__(self, db: Database):
        self.db = db
        self.audit = AuditService(db)

    def create_belief(
        self,
        claim_text: str,
        confidence: float = 0.5,
        decay_model: DecayModel = DecayModel.EXPONENTIAL,
        derived_from_agent: str = "",
        scope: dict | None = None,
    ) -> Belief:
        """Create a new belief with status=proposed."""
        belief = Belief(
            claim_text=claim_text,
            status=BeliefStatus.PROPOSED,
            confidence=confidence,
            decay_model=decay_model,
            derived_from_agent=derived_from_agent,
            scope=scope or {},
        )
        self.db.execute(
            "INSERT INTO beliefs (belief_id, claim_text, status, confidence, "
            "created_at, updated_at, decay_model, scope, derived_from_agent) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                belief.belief_id,
                belief.claim_text,
                belief.status.value,
                belief.confidence,
                belief.created_at.isoformat(),
                belief.updated_at.isoformat(),
                belief.decay_model.value,
                json.dumps(belief.scope),
                belief.derived_from_agent,
            ),
        )
        self.db.conn.commit()
        self.audit.log(
            "belief", belief.belief_id, "create",
            new_value=belief.model_dump(mode="json"),
        )
        return belief

    def get_belief(self, belief_id: str) -> Belief | None:
        row = self.db.fetchone("SELECT * FROM beliefs WHERE belief_id = ?", (belief_id,))
        if row is None:
            return None
        return self._row_to_belief(row)

    def list_beliefs(
        self, status: BeliefStatus | None = None, limit: int = 50
    ) -> list[Belief]:
        if status:
            rows = self.db.fetchall(
                "SELECT * FROM beliefs WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
                (status.value, limit),
            )
        else:
            rows = self.db.fetchall(
                "SELECT * FROM beliefs ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
        return [self._row_to_belief(r) for r in rows]

    def transition(self, belief_id: str, new_status: BeliefStatus) -> Belief:
        """Transition a belief to a new status. Validates the transition."""
        belief = self.get_belief(belief_id)
        if belief is None:
            raise ValueError(f"Belief {belief_id} not found")

        allowed = _VALID_TRANSITIONS.get(belief.status, set())
        if new_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition from {belief.status.value} to {new_status.value}. "
                f"Allowed: {[s.value for s in allowed]}"
            )

        old_value = belief.model_dump(mode="json")
        now = datetime.now(timezone.utc).isoformat()

        self.db.execute(
            "UPDATE beliefs SET status = ?, updated_at = ? WHERE belief_id = ?",
            (new_status.value, now, belief_id),
        )
        self.db.conn.commit()

        updated = self.get_belief(belief_id)
        self.audit.log(
            "belief", belief_id, "transition",
            old_value=old_value,
            new_value=updated.model_dump(mode="json"),
        )
        return updated

    def update_confidence(self, belief_id: str, confidence: float) -> Belief:
        """Update a belief's confidence score."""
        belief = self.get_belief(belief_id)
        if belief is None:
            raise ValueError(f"Belief {belief_id} not found")

        old_value = belief.model_dump(mode="json")
        confidence = max(0.0, min(1.0, confidence))
        now = datetime.now(timezone.utc).isoformat()

        self.db.execute(
            "UPDATE beliefs SET confidence = ?, updated_at = ? WHERE belief_id = ?",
            (confidence, now, belief_id),
        )
        self.db.conn.commit()

        updated = self.get_belief(belief_id)
        self.audit.log(
            "belief", belief_id, "confidence_update",
            old_value=old_value,
            new_value=updated.model_dump(mode="json"),
        )
        return updated

    def _row_to_belief(self, row) -> Belief:
        return Belief(
            belief_id=row["belief_id"],
            claim_text=row["claim_text"],
            status=BeliefStatus(row["status"]),
            confidence=row["confidence"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            decay_model=DecayModel(row["decay_model"]),
            scope=json.loads(row["scope"]),
            derived_from_agent=row["derived_from_agent"],
        )
