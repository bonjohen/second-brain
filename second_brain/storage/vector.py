"""Vector embedding storage and similarity search."""

from __future__ import annotations

import logging

import numpy as np

from second_brain.storage.sqlite import Database

logger = logging.getLogger(__name__)


class VectorStore:
    """Manages vector embeddings for semantic similarity search."""

    MODEL_NAME = "all-MiniLM-L6-v2"

    def __init__(self, db: Database) -> None:
        self._db = db
        self._model = None

    def _get_model(self):
        """Lazy-load the sentence-transformer model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.MODEL_NAME)
        return self._model

    def compute_embedding(self, text: str) -> np.ndarray:
        """Compute embedding vector for the given text."""
        model = self._get_model()
        return model.encode(text, convert_to_numpy=True)

    def store_embedding(self, note_id: str, embedding: np.ndarray) -> None:
        """Store an embedding for a note (INSERT OR REPLACE)."""
        self._db.execute(
            "INSERT OR REPLACE INTO embeddings (note_id, embedding, model) VALUES (?, ?, ?)",
            (note_id, embedding.tobytes(), self.MODEL_NAME),
        )

    def get_embedding(self, note_id: str) -> np.ndarray | None:
        """Retrieve the embedding for a note, or None if not stored."""
        row = self._db.fetchone(
            "SELECT embedding FROM embeddings WHERE note_id = ?",
            (note_id,),
        )
        if row is None:
            return None
        return np.frombuffer(row["embedding"], dtype=np.float32)

    def search_similar(
        self, query_text: str, top_k: int = 5, max_candidates: int = 10_000
    ) -> list[tuple[str, float]]:
        """Find the most similar notes to the query text.

        Returns list of (note_id, similarity_score) sorted by descending similarity.
        """
        query_embedding = self.compute_embedding(query_text)

        rows = self._db.fetchall(
            "SELECT note_id, embedding FROM embeddings LIMIT ?",
            (max_candidates,),
        )
        if not rows:
            return []

        if len(rows) == max_candidates:
            logger.warning(
                "search_similar hit max_candidates=%d; results may be incomplete",
                max_candidates,
            )

        results: list[tuple[str, float]] = []
        for row in rows:
            stored = np.frombuffer(row["embedding"], dtype=np.float32)
            score = self.cosine_similarity(query_embedding, stored)
            results.append((row["note_id"], float(score)))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def rebuild_index(self, notes_service) -> int:
        """Recompute embeddings for all notes. Returns count of notes indexed."""
        offset = 0
        batch_size = 1000
        count = 0
        while True:
            batch = notes_service.list_notes(limit=batch_size, offset=offset)
            if not batch:
                break
            for note in batch:
                embedding = self.compute_embedding(note.content)
                self.store_embedding(str(note.note_id), embedding)
                count += 1
            offset += batch_size
        return count

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
