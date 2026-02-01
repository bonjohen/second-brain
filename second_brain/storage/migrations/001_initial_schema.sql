-- Migration 001: Initial schema — all 5 core tables + audit_log + FTS5

CREATE TABLE IF NOT EXISTS sources (
    source_id   TEXT PRIMARY KEY,
    kind        TEXT NOT NULL CHECK(kind IN ('user', 'file', 'url', 'clipboard')),
    locator     TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    trust_label TEXT NOT NULL DEFAULT 'user' CHECK(trust_label IN ('user', 'trusted', 'unknown'))
);

CREATE TABLE IF NOT EXISTS notes (
    note_id      TEXT PRIMARY KEY,
    created_at   TEXT NOT NULL,
    content      TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'text' CHECK(content_type IN ('text', 'markdown', 'pdf', 'transcript', 'code')),
    source_id    TEXT NOT NULL REFERENCES sources(source_id),
    tags         TEXT NOT NULL DEFAULT '[]',       -- JSON array
    entities     TEXT NOT NULL DEFAULT '[]',       -- JSON array
    content_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS beliefs (
    belief_id          TEXT PRIMARY KEY,
    claim_text         TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'proposed' CHECK(status IN ('proposed', 'active', 'challenged', 'deprecated', 'archived')),
    confidence         REAL NOT NULL DEFAULT 0.5 CHECK(confidence >= 0.0 AND confidence <= 1.0),
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    decay_model        TEXT NOT NULL DEFAULT 'exponential' CHECK(decay_model IN ('exponential', 'none')),
    scope              TEXT NOT NULL DEFAULT '{}',  -- JSON object
    derived_from_agent TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS edges (
    edge_id   TEXT PRIMARY KEY,
    from_type TEXT NOT NULL CHECK(from_type IN ('note', 'belief', 'source')),
    from_id   TEXT NOT NULL,
    rel_type  TEXT NOT NULL CHECK(rel_type IN ('supports', 'contradicts', 'derived_from', 'related')),
    to_type   TEXT NOT NULL CHECK(to_type IN ('note', 'belief', 'source')),
    to_id     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signals (
    signal_id    TEXT PRIMARY KEY,
    type         TEXT NOT NULL,
    payload      TEXT NOT NULL DEFAULT '{}',  -- JSON object
    created_at   TEXT NOT NULL,
    processed_at TEXT  -- NULL until processed
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id    TEXT PRIMARY KEY,
    timestamp   TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    action      TEXT NOT NULL,
    old_value   TEXT,  -- JSON or NULL
    new_value   TEXT   -- JSON or NULL
);

-- Full-text search on notes
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    content,
    tags,
    entities,
    content='notes',
    content_rowid='rowid'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid, content, tags, entities)
    VALUES (new.rowid, new.content, new.tags, new.entities);
END;

-- Index for common queries
CREATE INDEX IF NOT EXISTS idx_notes_source ON notes(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_type, from_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_type, to_id);
CREATE INDEX IF NOT EXISTS idx_signals_unprocessed ON signals(processed_at) WHERE processed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_beliefs_status ON beliefs(status);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);
