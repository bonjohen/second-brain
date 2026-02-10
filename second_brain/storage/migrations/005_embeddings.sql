-- Phase 1: Embeddings table for vector similarity search
CREATE TABLE IF NOT EXISTS embeddings (
    note_id     TEXT PRIMARY KEY REFERENCES notes(note_id),
    embedding   BLOB NOT NULL,
    model       TEXT NOT NULL
);
