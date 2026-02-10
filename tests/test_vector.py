"""Tests for VectorStore with mocked sentence-transformer model."""

import uuid
from unittest.mock import MagicMock

import numpy as np

from second_brain.storage.vector import VectorStore


class TestVectorStore:
    def _make_store(self, db):
        """Create a VectorStore with a mocked model."""
        store = VectorStore(db)
        mock_model = MagicMock()
        # Return deterministic embeddings based on input
        mock_model.encode.side_effect = lambda text, **kwargs: np.array(
            [hash(text) % 100 / 100.0] * 384, dtype=np.float32
        )
        store._model = mock_model
        return store

    def _create_note(self, note_service):
        """Create a real note and return its ID as a string."""
        source = note_service.create_source(kind="user", locator="test")
        note = note_service.create_note(
            "Test note content", content_type="text", source_id=source.source_id
        )
        return str(note.note_id)

    def test_compute_embedding(self, db):
        store = self._make_store(db)
        embedding = store.compute_embedding("hello world")
        assert isinstance(embedding, np.ndarray)
        assert len(embedding) == 384

    def test_store_and_retrieve_embedding(self, db, note_service):
        store = self._make_store(db)
        note_id = self._create_note(note_service)
        embedding = np.random.rand(384).astype(np.float32)
        store.store_embedding(note_id, embedding)

        retrieved = store.get_embedding(note_id)
        assert retrieved is not None
        np.testing.assert_array_almost_equal(retrieved, embedding)

    def test_get_embedding_not_found(self, db):
        store = self._make_store(db)
        result = store.get_embedding(str(uuid.uuid4()))
        assert result is None

    def test_store_embedding_replace(self, db, note_service):
        store = self._make_store(db)
        note_id = self._create_note(note_service)
        e1 = np.ones(384, dtype=np.float32)
        e2 = np.zeros(384, dtype=np.float32)

        store.store_embedding(note_id, e1)
        store.store_embedding(note_id, e2)

        retrieved = store.get_embedding(note_id)
        np.testing.assert_array_almost_equal(retrieved, e2)

    def test_search_similar(self, db, note_service):
        store = self._make_store(db)
        id1 = self._create_note(note_service)
        id2 = self._create_note(note_service)
        id3 = self._create_note(note_service)

        store.store_embedding(id1, np.ones(384, dtype=np.float32))
        store.store_embedding(id2, np.ones(384, dtype=np.float32) * 0.5)
        store.store_embedding(id3, -np.ones(384, dtype=np.float32))

        # Mock compute_embedding for query to return ones (similar to id1)
        store._model.encode.side_effect = lambda text, **kwargs: np.ones(
            384, dtype=np.float32
        )

        results = store.search_similar("test query", top_k=2)
        assert len(results) == 2
        # First result should be most similar (id1 or id2)
        assert results[0][1] >= results[1][1]

    def test_search_similar_empty(self, db):
        store = self._make_store(db)
        store._model.encode.side_effect = lambda text, **kwargs: np.ones(
            384, dtype=np.float32
        )
        results = store.search_similar("test query")
        assert results == []

    def test_cosine_similarity_identical(self):
        a = np.ones(10, dtype=np.float32)
        score = VectorStore._cosine_similarity(a, a)
        assert abs(score - 1.0) < 1e-6

    def test_cosine_similarity_opposite(self):
        a = np.ones(10, dtype=np.float32)
        b = -np.ones(10, dtype=np.float32)
        score = VectorStore._cosine_similarity(a, b)
        assert abs(score - (-1.0)) < 1e-6

    def test_cosine_similarity_zero_vector(self):
        a = np.zeros(10, dtype=np.float32)
        b = np.ones(10, dtype=np.float32)
        score = VectorStore._cosine_similarity(a, b)
        assert score == 0.0

    def test_rebuild_index(self, db, note_service):
        store = self._make_store(db)
        # Create some notes
        source = note_service.create_source(kind="user", locator="test")
        note_service.create_note("First note", content_type="text", source_id=source.source_id)
        note_service.create_note("Second note", content_type="text", source_id=source.source_id)

        count = store.rebuild_index(note_service)
        assert count == 2

    def test_lazy_load_model(self, db):
        """Verify model is not loaded on construction."""
        store = VectorStore(db)
        assert store._model is None
