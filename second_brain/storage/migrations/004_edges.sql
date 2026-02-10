-- Phase 1: Edges table (polymorphic relationships)
CREATE TABLE IF NOT EXISTS edges (
    edge_id     TEXT PRIMARY KEY,
    from_type   TEXT NOT NULL CHECK (from_type IN ('note', 'belief', 'source')),
    from_id     TEXT NOT NULL,
    rel_type    TEXT NOT NULL CHECK (rel_type IN ('supports', 'contradicts', 'derived_from', 'related_to')),
    to_type     TEXT NOT NULL CHECK (to_type IN ('note', 'belief', 'source')),
    to_id       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_edges_from ON edges (from_type, from_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON edges (to_type, to_id);
CREATE INDEX IF NOT EXISTS idx_edges_rel_type ON edges (rel_type);
