-- Migration 001: Initial schema for Phase 0

CREATE TABLE IF NOT EXISTS sources (
    source_id   TEXT PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind IN ('user', 'file', 'url', 'clipboard')),
    locator     TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    trust_label TEXT NOT NULL DEFAULT 'unknown'
                CHECK (trust_label IN ('user', 'trusted', 'unknown'))
);

CREATE TABLE IF NOT EXISTS notes (
    note_id      TEXT PRIMARY KEY,
    created_at   TEXT NOT NULL,
    content      TEXT NOT NULL,
    content_type TEXT NOT NULL CHECK (content_type IN ('text', 'markdown', 'pdf', 'transcript', 'code')),
    source_id    TEXT NOT NULL REFERENCES sources(source_id),
    tags         TEXT NOT NULL DEFAULT '[]',
    entities     TEXT NOT NULL DEFAULT '[]',
    content_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notes_source_id ON notes(source_id);
CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes(created_at);
CREATE INDEX IF NOT EXISTS idx_notes_content_hash ON notes(content_hash);

CREATE TABLE IF NOT EXISTS signals (
    signal_id    TEXT PRIMARY KEY,
    type         TEXT NOT NULL,
    payload      TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL,
    processed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_signals_type_unprocessed
    ON signals(type) WHERE processed_at IS NULL;

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id    TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    action      TEXT NOT NULL,
    before_json TEXT,
    after_json  TEXT,
    timestamp   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_entity
    ON audit_log(entity_type, entity_id);
