"""Belief persistence service with lifecycle management."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from second_brain.core.constants import DEFAULT_BASE_CONFIDENCE
from second_brain.core.models import Belief, BeliefStatus, DecayModel
from second_brain.core.services.audit import AuditService
from second_brain.core.services.edges import EdgeService
from second_brain.core.utils import safe_json_loads
from second_brain.storage.sqlite import Database

# Valid status transitions
_VALID_TRANSITIONS: dict[BeliefStatus, set[BeliefStatus]] = {
    BeliefStatus.PROPOSED: {BeliefStatus.ACTIVE},
    BeliefStatus.ACTIVE: {BeliefStatus.CHALLENGED},
    BeliefStatus.CHALLENGED: {BeliefStatus.ACTIVE, BeliefStatus.DEPRECATED},
    BeliefStatus.DEPRECATED: {BeliefStatus.ARCHIVED},
    BeliefStatus.ARCHIVED: set(),
}


class BeliefService:
    def __init__(
        self,
        db: Database,
        audit: AuditService,
        edge_service: EdgeService,
    ) -> None:
        self._db = db
        self._audit = audit
        self._edges = edge_service

    def create_belief(
        self,
        claim_text: str,
        confidence: float = DEFAULT_BASE_CONFIDENCE,
        derived_from_agent: str = "",
        decay_model: DecayModel = DecayModel.EXPONENTIAL,
        scope: dict[str, Any] | None = None,
    ) -> Belief:
        """Create and persist a new belief."""
        belief = Belief(
            claim_text=claim_text,
            confidence=confidence,
            derived_from_agent=derived_from_agent,
            decay_model=decay_model,
            scope=scope or {},
        )
        self._db.execute(
            """
            INSERT INTO beliefs
                (belief_id, claim_text, status, confidence, created_at, updated_at,
                 decay_model, scope, derived_from_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(belief.belief_id),
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
        self._audit.log_event(
            entity_type="belief",
            entity_id=belief.belief_id,
            action="created",
            after=belief.model_dump(mode="json"),
        )
        return belief

    def update_belief_status(
        self,
        belief_id: uuid.UUID,
        new_status: BeliefStatus,
    ) -> Belief:
        """Transition a belief's status. Validates allowed transitions."""
        belief = self.get_belief(belief_id)
        if belief is None:
            raise ValueError(f"Belief not found: {belief_id}")

        allowed = _VALID_TRANSITIONS.get(belief.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid transition: {belief.status.value} -> {new_status.value}"
            )

        before = belief.model_dump(mode="json")
        now = datetime.now(UTC)
        self._db.execute(
            "UPDATE beliefs SET status = ?, updated_at = ? WHERE belief_id = ?",
            (new_status.value, now.isoformat(), str(belief_id)),
        )
        updated = self.get_belief(belief_id)
        self._audit.log_event(
            entity_type="belief",
            entity_id=belief_id,
            action="status_changed",
            before=before,
            after=updated.model_dump(mode="json"),
        )
        return updated

    def update_confidence(
        self,
        belief_id: uuid.UUID,
        new_confidence: float,
    ) -> Belief:
        """Update a belief's confidence, clamped to [0, 1]."""
        belief = self.get_belief(belief_id)
        if belief is None:
            raise ValueError(f"Belief not found: {belief_id}")

        clamped = max(0.0, min(1.0, new_confidence))
        before = belief.model_dump(mode="json")
        now = datetime.now(UTC)
        self._db.execute(
            "UPDATE beliefs SET confidence = ?, updated_at = ? WHERE belief_id = ?",
            (clamped, now.isoformat(), str(belief_id)),
        )
        updated = self.get_belief(belief_id)
        self._audit.log_event(
            entity_type="belief",
            entity_id=belief_id,
            action="confidence_updated",
            before=before,
            after=updated.model_dump(mode="json"),
        )
        return updated

    def get_belief(self, belief_id: uuid.UUID) -> Belief | None:
        """Retrieve a belief by ID."""
        row = self._db.fetchone(
            "SELECT * FROM beliefs WHERE belief_id = ?",
            (str(belief_id),),
        )
        if row is None:
            return None
        return self._row_to_belief(row)

    def list_beliefs(
        self,
        status_filter: BeliefStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Belief]:
        """List beliefs with optional status filter."""
        if status_filter:
            rows = self._db.fetchall(
                "SELECT * FROM beliefs WHERE status = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (status_filter.value, limit, offset),
            )
        else:
            rows = self._db.fetchall(
                "SELECT * FROM beliefs ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        return [self._row_to_belief(row) for row in rows]

    @staticmethod
    def _row_to_belief(row: Any) -> Belief:
        return Belief(
            belief_id=uuid.UUID(row["belief_id"]),
            claim_text=row["claim_text"],
            status=BeliefStatus(row["status"]),
            confidence=row["confidence"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            decay_model=DecayModel(row["decay_model"]),
            scope=safe_json_loads(row["scope"], default={}, context="belief.scope"),
            derived_from_agent=row["derived_from_agent"],
        )
