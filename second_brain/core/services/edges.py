"""Edge service — typed graph relationships with referential integrity."""

from __future__ import annotations

from second_brain.core.models import Edge, EdgeFromType, EdgeRelType, EdgeToType
from second_brain.storage.sqlite import Database

# Maps entity types to their table and PK column
_TYPE_TABLE = {
    "note": ("notes", "note_id"),
    "belief": ("beliefs", "belief_id"),
    "source": ("sources", "source_id"),
}


class EdgeService:
    def __init__(self, db: Database):
        self.db = db

    def create_edge(
        self,
        from_type: EdgeFromType,
        from_id: str,
        rel_type: EdgeRelType,
        to_type: EdgeToType,
        to_id: str,
    ) -> Edge:
        """Create an edge with referential integrity checks."""
        # Verify both endpoints exist
        self._verify_exists(from_type.value, from_id)
        self._verify_exists(to_type.value, to_id)

        edge = Edge(
            from_type=from_type,
            from_id=from_id,
            rel_type=rel_type,
            to_type=to_type,
            to_id=to_id,
        )
        self.db.execute(
            "INSERT INTO edges (edge_id, from_type, from_id, rel_type, to_type, to_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                edge.edge_id,
                edge.from_type.value,
                edge.from_id,
                edge.rel_type.value,
                edge.to_type.value,
                edge.to_id,
            ),
        )
        self.db.conn.commit()
        return edge

    def get_edge(self, edge_id: str) -> Edge | None:
        row = self.db.fetchone("SELECT * FROM edges WHERE edge_id = ?", (edge_id,))
        if row is None:
            return None
        return self._row_to_edge(row)

    def get_edges_from(
        self, from_type: str, from_id: str, rel_type: str | None = None
    ) -> list[Edge]:
        """Get all edges originating from a given entity."""
        if rel_type:
            rows = self.db.fetchall(
                "SELECT * FROM edges WHERE from_type = ? AND from_id = ? AND rel_type = ?",
                (from_type, from_id, rel_type),
            )
        else:
            rows = self.db.fetchall(
                "SELECT * FROM edges WHERE from_type = ? AND from_id = ?",
                (from_type, from_id),
            )
        return [self._row_to_edge(r) for r in rows]

    def get_edges_to(
        self, to_type: str, to_id: str, rel_type: str | None = None
    ) -> list[Edge]:
        """Get all edges pointing to a given entity."""
        if rel_type:
            rows = self.db.fetchall(
                "SELECT * FROM edges WHERE to_type = ? AND to_id = ? AND rel_type = ?",
                (to_type, to_id, rel_type),
            )
        else:
            rows = self.db.fetchall(
                "SELECT * FROM edges WHERE to_type = ? AND to_id = ?",
                (to_type, to_id),
            )
        return [self._row_to_edge(r) for r in rows]

    def get_support_edges(self, belief_id: str) -> list[Edge]:
        """Get edges that support a belief."""
        return self.get_edges_to("belief", belief_id, "supports")

    def get_contradiction_edges(self, belief_id: str) -> list[Edge]:
        """Get edges that contradict a belief."""
        return self.get_edges_to("belief", belief_id, "contradicts")

    def _verify_exists(self, entity_type: str, entity_id: str) -> None:
        table, pk_col = _TYPE_TABLE[entity_type]
        row = self.db.fetchone(
            f"SELECT 1 FROM {table} WHERE {pk_col} = ?", (entity_id,)
        )
        if row is None:
            raise ValueError(f"{entity_type} {entity_id} does not exist")

    def _row_to_edge(self, row) -> Edge:
        return Edge(
            edge_id=row["edge_id"],
            from_type=EdgeFromType(row["from_type"]),
            from_id=row["from_id"],
            rel_type=EdgeRelType(row["rel_type"]),
            to_type=EdgeToType(row["to_type"]),
            to_id=row["to_id"],
        )
