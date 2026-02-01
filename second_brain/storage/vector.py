"""Vector storage — local embeddings with cosine similarity.

Uses a simple numpy-based approach stored in SQLite as a BLOB.
sentence-transformers is optional — falls back to a basic TF-IDF-like approach
if not available.
"""

from __future__ import annotations

import json
import math
import struct
from collections import Counter

from second_brain.storage.sqlite import Database

# Try to import sentence-transformers; fall back to basic embeddings
_ST_AVAILABLE = False
_model = None

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    _ST_AVAILABLE = True
except ImportError:
    pass


def _ensure_table(db: Database) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS embeddings ("
        "  entity_id TEXT PRIMARY KEY,"
        "  entity_type TEXT NOT NULL,"
        "  vector BLOB NOT NULL,"
        "  dims INTEGER NOT NULL"
        ")"
    )
    db.conn.commit()


def _get_model():
    global _model
    if _model is None and _ST_AVAILABLE:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _encode_vector(vec: list[float]) -> bytes:
    """Pack float list to bytes."""
    return struct.pack(f"{len(vec)}f", *vec)


def _decode_vector(data: bytes, dims: int) -> list[float]:
    """Unpack bytes to float list."""
    return list(struct.unpack(f"{dims}f", data))


def _basic_embedding(text: str, dims: int = 128) -> list[float]:
    """Simple bag-of-words hashing embedding for when sentence-transformers is not available."""
    words = text.lower().split()
    counts = Counter(words)
    vec = [0.0] * dims
    for word, count in counts.items():
        idx = hash(word) % dims
        vec[idx] += count
    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


class VectorStore:
    def __init__(self, db: Database):
        self.db = db
        _ensure_table(db)

    def store_embedding(self, entity_id: str, entity_type: str, text: str) -> None:
        """Compute and store embedding for given text."""
        vec = self._embed(text)
        blob = _encode_vector(vec)
        self.db.execute(
            "INSERT OR REPLACE INTO embeddings (entity_id, entity_type, vector, dims) "
            "VALUES (?, ?, ?, ?)",
            (entity_id, entity_type, blob, len(vec)),
        )
        self.db.conn.commit()

    def search_similar(
        self, query: str, entity_type: str | None = None, limit: int = 10
    ) -> list[tuple[str, float]]:
        """Find entities most similar to query. Returns list of (entity_id, score)."""
        query_vec = self._embed(query)

        if entity_type:
            rows = self.db.fetchall(
                "SELECT entity_id, vector, dims FROM embeddings WHERE entity_type = ?",
                (entity_type,),
            )
        else:
            rows = self.db.fetchall("SELECT entity_id, vector, dims FROM embeddings")

        scored = []
        for row in rows:
            stored_vec = _decode_vector(row["vector"], row["dims"])
            score = _cosine_similarity(query_vec, stored_vec)
            scored.append((row["entity_id"], score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    def get_embedding(self, entity_id: str) -> list[float] | None:
        row = self.db.fetchone(
            "SELECT vector, dims FROM embeddings WHERE entity_id = ?", (entity_id,)
        )
        if row is None:
            return None
        return _decode_vector(row["vector"], row["dims"])

    def rebuild_all(self, notes_with_content: list[tuple[str, str]]) -> int:
        """Rebuild all note embeddings from scratch. Returns count."""
        self.db.execute("DELETE FROM embeddings WHERE entity_type = 'note'")
        count = 0
        for note_id, content in notes_with_content:
            self.store_embedding(note_id, "note", content)
            count += 1
        return count

    def _embed(self, text: str) -> list[float]:
        model = _get_model()
        if model is not None:
            vec = model.encode(text, normalize_embeddings=True)
            return vec.tolist()
        return _basic_embedding(text)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b):
        # Pad shorter vector with zeros
        max_len = max(len(a), len(b))
        a = a + [0.0] * (max_len - len(a))
        b = b + [0.0] * (max_len - len(b))

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
