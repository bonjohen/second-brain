"""Tests for EdgeService."""

import uuid

from second_brain.core.models import EntityType, RelType


class TestEdgeService:
    def test_create_edge(self, edge_service):
        note_id = uuid.uuid4()
        belief_id = uuid.uuid4()
        edge = edge_service.create_edge(
            from_type=EntityType.NOTE,
            from_id=note_id,
            rel_type=RelType.SUPPORTS,
            to_type=EntityType.BELIEF,
            to_id=belief_id,
        )
        assert edge.from_type == EntityType.NOTE
        assert edge.from_id == note_id
        assert edge.rel_type == RelType.SUPPORTS
        assert edge.to_type == EntityType.BELIEF
        assert edge.to_id == belief_id

    def test_get_edges_outgoing(self, edge_service):
        note_id = uuid.uuid4()
        b1 = uuid.uuid4()
        b2 = uuid.uuid4()
        edge_service.create_edge(EntityType.NOTE, note_id, RelType.SUPPORTS, EntityType.BELIEF, b1)
        edge_service.create_edge(EntityType.NOTE, note_id, RelType.SUPPORTS, EntityType.BELIEF, b2)

        edges = edge_service.get_edges(EntityType.NOTE, note_id, direction="outgoing")
        assert len(edges) == 2

    def test_get_edges_incoming(self, edge_service):
        belief_id = uuid.uuid4()
        n1 = uuid.uuid4()
        n2 = uuid.uuid4()
        edge_service.create_edge(
            EntityType.NOTE, n1, RelType.SUPPORTS, EntityType.BELIEF, belief_id
        )
        edge_service.create_edge(
            EntityType.NOTE, n2, RelType.CONTRADICTS, EntityType.BELIEF, belief_id
        )

        edges = edge_service.get_edges(EntityType.BELIEF, belief_id, direction="incoming")
        assert len(edges) == 2

    def test_get_edges_both_directions(self, edge_service):
        entity_id = uuid.uuid4()
        other1 = uuid.uuid4()
        other2 = uuid.uuid4()
        edge_service.create_edge(
            EntityType.NOTE, entity_id, RelType.SUPPORTS, EntityType.BELIEF, other1
        )
        edge_service.create_edge(
            EntityType.BELIEF, other2, RelType.CONTRADICTS, EntityType.NOTE, entity_id
        )

        edges = edge_service.get_edges(EntityType.NOTE, entity_id)
        assert len(edges) == 2

    def test_get_edges_filter_by_rel_type(self, edge_service):
        note_id = uuid.uuid4()
        b1 = uuid.uuid4()
        b2 = uuid.uuid4()
        edge_service.create_edge(
            EntityType.NOTE, note_id, RelType.SUPPORTS, EntityType.BELIEF, b1
        )
        edge_service.create_edge(
            EntityType.NOTE, note_id, RelType.CONTRADICTS, EntityType.BELIEF, b2
        )

        supports = edge_service.get_edges(
            EntityType.NOTE, note_id, direction="outgoing", rel_type=RelType.SUPPORTS
        )
        assert len(supports) == 1
        assert supports[0].rel_type == RelType.SUPPORTS

    def test_delete_edge(self, edge_service):
        note_id = uuid.uuid4()
        belief_id = uuid.uuid4()
        edge = edge_service.create_edge(
            EntityType.NOTE, note_id, RelType.SUPPORTS, EntityType.BELIEF, belief_id
        )
        edge_service.delete_edge(edge.edge_id)

        edges = edge_service.get_edges(EntityType.NOTE, note_id)
        assert len(edges) == 0

    def test_get_edges_empty(self, edge_service):
        edges = edge_service.get_edges(EntityType.NOTE, uuid.uuid4())
        assert edges == []
