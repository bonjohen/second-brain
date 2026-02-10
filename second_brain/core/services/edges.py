"""Edge persistence service for polymorphic relationships."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from second_brain.core.models import Edge, EntityType, RelType
from second_brain.storage.sqlite import Database


class EdgeService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create_edge(
        self,
        from_type: EntityType,
        from_id: uuid.UUID,
        rel_type: RelType,
        to_type: EntityType,
        to_id: uuid.UUID,
    ) -> Edge:
        """Create and persist an edge between two entities."""
        edge = Edge(
            from_type=from_type,
            from_id=from_id,
            rel_type=rel_type,
            to_type=to_type,
            to_id=to_id,
        )
        self._db.execute(
            """
            INSERT INTO edges (edge_id, from_type, from_id, rel_type, to_type, to_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(edge.edge_id),
                edge.from_type.value,
                str(edge.from_id),
                edge.rel_type.value,
                edge.to_type.value,
                str(edge.to_id),
            ),
        )
        return edge

    def get_edges(
        self,
        entity_type: EntityType,
        entity_id: uuid.UUID,
        direction: Literal["outgoing", "incoming"] | None = None,
        rel_type: RelType | None = None,
    ) -> list[Edge]:
        """Get edges for an entity.

        direction: "outgoing" (from), "incoming" (to), or None (both).
        """
        if direction is not None and direction not in ("outgoing", "incoming"):
            raise ValueError(
                f"Invalid direction: {direction!r}; expected 'outgoing', 'incoming', or None"
            )

        conditions: list[str] = []
        params: list[Any] = []

        if direction == "outgoing":
            conditions.append("from_type = ? AND from_id = ?")
            params.extend([entity_type.value, str(entity_id)])
        elif direction == "incoming":
            conditions.append("to_type = ? AND to_id = ?")
            params.extend([entity_type.value, str(entity_id)])
        else:
            conditions.append(
                "((from_type = ? AND from_id = ?) OR (to_type = ? AND to_id = ?))"
            )
            params.extend([
                entity_type.value,
                str(entity_id),
                entity_type.value,
                str(entity_id),
            ])

        if rel_type:
            conditions.append("rel_type = ?")
            params.append(rel_type.value)

        where = " AND ".join(conditions)
        # SAFETY: {where} only contains static SQL fragments built above;
        # all user-supplied values use parameterized ? placeholders in params.
        rows = self._db.fetchall(
            f"SELECT * FROM edges WHERE {where}",
            tuple(params),
        )
        return [self._row_to_edge(row) for row in rows]

    def delete_edge(self, edge_id: uuid.UUID) -> bool:
        """Delete an edge by ID. Returns True if an edge was deleted, False if not found."""
        cursor = self._db.execute(
            "DELETE FROM edges WHERE edge_id = ?",
            (str(edge_id),),
        )
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_edge(row: Any) -> Edge:
        return Edge(
            edge_id=uuid.UUID(row["edge_id"]),
            from_type=EntityType(row["from_type"]),
            from_id=uuid.UUID(row["from_id"]),
            rel_type=RelType(row["rel_type"]),
            to_type=EntityType(row["to_type"]),
            to_id=uuid.UUID(row["to_id"]),
        )
