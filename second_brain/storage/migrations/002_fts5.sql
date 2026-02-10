-- Migration 002: Full-text search via FTS5

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    note_id UNINDEXED,
    content,
    tags,
    entities,
    content=notes,
    content_rowid=rowid
);

-- Keep FTS index in sync with notes table

CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid, note_id, content, tags, entities)
    VALUES (new.rowid, new.note_id, new.content, new.tags, new.entities);
END;

-- Notes are immutable, so no UPDATE trigger needed.
-- DELETE trigger for completeness (curator phase).
CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, note_id, content, tags, entities)
    VALUES ('delete', old.rowid, old.note_id, old.content, old.tags, old.entities);
END;
