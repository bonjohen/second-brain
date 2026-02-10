-- Phase 1: Beliefs table
CREATE TABLE IF NOT EXISTS beliefs (
    belief_id       TEXT PRIMARY KEY,
    claim_text      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'proposed'
                    CHECK (status IN ('proposed', 'active', 'challenged', 'deprecated', 'archived')),
    confidence      REAL NOT NULL DEFAULT 0.5
                    CHECK (confidence >= 0.0 AND confidence <= 1.0),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    decay_model     TEXT NOT NULL DEFAULT 'exponential'
                    CHECK (decay_model IN ('exponential', 'none')),
    scope           TEXT NOT NULL DEFAULT '{}',
    derived_from_agent TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_beliefs_status ON beliefs (status);
CREATE INDEX IF NOT EXISTS idx_beliefs_updated_at ON beliefs (updated_at);
