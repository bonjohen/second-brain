# SECOND BRAIN — PHASED TODO LIST

Derived from [PDR.MD](PDR.MD). Each task is a discrete, completable unit of work.
Mark tasks `[~]` as they are started.
Mark tasks `[x]` as they are finished.

---

## Phase 0 — Foundation & Capture

The goal of this phase is to stand up the project skeleton, storage layer, and basic note capture. At exit, notes persist, are searchable, and every mutation is audited.

### 0.1 Project Scaffolding

- [x] Create the full directory structure per PDR Section 4.1
  - `core/`, `core/services/`, `core/rules/`
  - `agents/`
  - `storage/`, `storage/migrations/`
  - `runtime/`
  - `cli/`
  - `tests/`
- [x] Add `__init__.py` files to all Python packages
- [x] Create `pyproject.toml` (or `setup.py`) with project metadata and dependency list
- [x] Set up a virtual environment and pin initial dependencies
- [x] Configure linting/formatting (ruff or black + isort)
- [x] Configure pytest and establish `tests/` conventions

### 0.2 Data Models

- [x] Implement `core/models.py` — define dataclasses/Pydantic models for:
  - Note (with UUID, timestamp, content, content_type enum, source_id, tags, entities, content_hash)
  - Source (with UUID, kind enum, locator, captured_at, trust_label enum)
  - Signal (with UUID, type, payload, created_at, processed_at)
- [x] Add enum definitions for content_type, source kind, and trust_label
- [x] Write unit tests for model creation and validation

### 0.3 SQLite Storage Layer

- [x] Implement `storage/sqlite.py` — database connection manager
  - Enforce WAL mode, foreign keys ON
  - Provide a context-managed connection/session interface
- [x] Create initial migration in `storage/migrations/` for tables:
  - `notes`
  - `sources`
  - `signals`
  - `audit_log`
- [x] Implement a lightweight migration runner (ordered SQL scripts)
- [x] Write tests: schema creation, foreign key enforcement, WAL mode verification

### 0.4 Core Services — Notes & Sources

- [x] Implement `core/services/notes.py`
  - `create_note(content, content_type, source_id, tags, entities)` — computes SHA-256 hash, persists, returns Note
  - `get_note(note_id)` — retrieve by UUID
  - `search_notes(query)` — FTS-backed keyword search
  - `list_notes(filters)` — list with optional tag/entity/date filters
- [x] Implement `core/services/signals.py`
  - `emit_signal(type, payload)` — persist a new Signal row
  - `get_unprocessed_signals(type)` — retrieve signals where processed_at is null
  - `mark_processed(signal_id)` — set processed_at timestamp
- [x] Write tests for note CRUD and signal lifecycle

### 0.5 Audit Service

- [x] Implement `core/services/audit.py`
  - Append-only audit log: `log_event(entity_type, entity_id, action, before, after)`
  - Query audit trail: `get_history(entity_type, entity_id)`
- [x] Write tests for audit log append and retrieval

### 0.6 Full-Text Search (FTS)

- [x] Add FTS5 virtual table for notes content in a migration
- [x] Wire FTS into `notes.search_notes(query)`
- [x] Write tests: indexing on insert, search relevance, empty results

### 0.7 CLI — Capture Commands

- [x] Implement `cli/main.py` using Click (or argparse)
- [x] `add` command — accepts text (stdin or argument), optional tags, source kind
  - Calls IngestionAgent (or directly calls note/source services for Phase 0)
  - Prints created note ID
- [x] `search` command — keyword query, prints matching notes with IDs and snippets
- [x] `show` command — display full note by ID with metadata
- [x] Write integration tests for each CLI command

### 0.8 IngestionAgent (Basic)

- [x] Implement `agents/ingestion.py`
  - Create Source record
  - Create Note record (immutable)
  - Extract tags/entities via regex + keyword list
  - Compute content_hash
  - Emit `signal:new_note`
- [x] Write tests for the full ingestion pipeline

### 0.9 Phase 0 Validation

- [x] End-to-end test: add a note via CLI, search for it, show it, verify audit log
- [x] Verify all state survives process restart (persistence test)
- [x] Verify no in-memory-only state exists

---

## Phase 1 — Reasoning

The goal of this phase is to introduce beliefs, edges, confidence management, contradiction detection, and the ask pipeline. At exit, beliefs are tracked, contradictions are handled, and answers are grounded in evidence.

### 1.1 Data Models — Beliefs & Edges

- [x] Add to `core/models.py`:
  - Belief (UUID, claim_text, status enum, confidence, timestamps, decay_model enum, scope, derived_from_agent)
  - Edge (UUID, from_type enum, from_id, rel_type enum, to_type enum, to_id)
- [x] Add enum definitions for belief status, decay_model, edge from/to types, rel_type
- [x] Write unit tests for model creation and validation

### 1.2 SQLite Schema — Beliefs & Edges

- [x] Create migration for `beliefs` table
- [x] Create migration for `edges` table with composite foreign-key-like referential checks
- [x] Write tests: schema constraints, referential integrity

### 1.3 Core Services — Beliefs & Edges

- [x] Implement `core/services/beliefs.py`
  - `create_belief(claim_text, confidence, derived_from_agent)` — status=proposed, log to audit
  - `update_belief_status(belief_id, new_status)` — enforce valid transitions per PDR Section 6.2, log to audit
  - `update_confidence(belief_id, new_confidence)` — clamp to [0.0, 1.0], log to audit
  - `get_belief(belief_id)` — retrieve by UUID
  - `list_beliefs(status_filter)` — list with optional status filter
- [x] Implement `core/services/edges.py`
  - `create_edge(from_type, from_id, rel_type, to_type, to_id)` — validate referential integrity, persist
  - `get_edges(entity_type, entity_id, direction, rel_type)` — query edges for an entity
  - `delete_edge(edge_id)`
- [x] Write tests for belief CRUD, status transition enforcement, edge CRUD

### 1.4 Confidence & Decay Rules

- [x] Implement `core/rules/confidence.py`
  - `compute_confidence(belief_id)` — apply formula from PDR Section 6.1:
    `clamp((sum(support_weights) - sum(counter_weights)) * decay(time), 0.0, 1.0)`
  - Support weight = 1.0 per supporting edge (extensible later)
  - Counter weight = 1.0 per contradicting edge
- [x] Implement `core/rules/decay.py`
  - `exponential_decay(time_since_last_update, half_life)` — returns multiplier
  - `no_decay()` — returns 1.0
  - Select decay function based on belief's `decay_model` field
- [x] Write tests: confidence calculation with various edge configurations, decay over time

### 1.5 Contradiction Rules

- [x] Implement `core/rules/contradictions.py`
  - `detect_contradictions(belief_id)` — check for:
    - Exact negation (string-level heuristic)
    - Same-subject opposing predicates
  - Return list of contradicting belief/note IDs
- [x] Write tests for contradiction detection heuristics

### 1.6 Vector Embeddings

- [x] Implement `storage/vector.py`
  - Embedding computation (local model, e.g. sentence-transformers)
  - Store embeddings alongside note IDs
  - `search_similar(query_embedding, top_k)` — cosine similarity search
  - `rebuild_index()` — full reindex from notes table
- [x] Update IngestionAgent to compute and store embeddings on note creation
- [x] Write tests: embedding storage, similarity search, index rebuild

### 1.7 SynthesisAgent

- [x] Implement `agents/synthesis.py`
  - Triggered by `signal:new_note` or scheduled run
  - Group notes by shared tags/entities
  - Generate belief candidates (string templates; LLM optional)
  - Create Belief with `status=proposed`
  - Create `supports` edges from source notes to new belief
  - Emit `signal:belief_proposed`
- [x] Write tests for the full synthesis pipeline

### 1.8 ChallengerAgent

- [x] Implement `agents/challenger.py`
  - Triggered by `signal:belief_proposed` and `signal:new_note`
  - Run contradiction detection on relevant beliefs
  - If contradiction found:
    - Create `contradicts` edge
    - Set belief status to `challenged`
    - Recompute confidence
    - Emit `signal:belief_challenged`
- [x] Write tests for challenge detection and state transitions

### 1.9 Ask Pipeline

- [x] Implement ask pipeline (in `cli/main.py` or a dedicated service)
  - Accept a natural-language question
  - Perform FTS keyword search
  - Perform vector similarity search
  - Retrieve active beliefs related to matching notes
  - Assemble evidence pack (notes + beliefs + edges)
  - Synthesize answer (template-based or LLM, with citations)
  - Validate that all claims cite evidence IDs
  - Output answer + evidence IDs
- [x] Add `ask` CLI command
- [x] Write tests: ask with known data returns grounded answer, uncited claims are rejected

### 1.10 Phase 1 Validation

- [x] End-to-end test: add multiple notes, verify beliefs are proposed, contradictions detected
- [x] End-to-end test: ask a question, verify answer cites stored evidence
- [x] Verify all belief transitions are logged in audit trail
- [x] Verify confidence recomputation after new evidence

---

## Phase 2 — Proactive

The goal of this phase is to make the system self-maintaining with scheduled background processing, curation, and full auditability. At exit, the system runs autonomously with snapshot/restore support.

### 2.1 Signal Dispatcher

- [ ] Implement `runtime/dispatcher.py`
  - Poll unprocessed signals
  - Route signals to registered agent handlers by signal type
  - Mark signals as processed after handling
  - Handle errors: log failures, do not mark as processed on error
- [ ] Write tests for dispatch routing, error handling, idempotency

### 2.2 Scheduler

- [ ] Implement `runtime/scheduler.py`
  - Configurable tick interval
  - On each tick, invoke agents in defined order: Curator, Challenger, Synthesis
  - Emit scheduling signals or call agents directly
  - Support run-once mode (for CLI invocation) and continuous mode
- [ ] Write tests for scheduling order, tick behavior

### 2.3 CuratorAgent

- [ ] Implement `agents/curator.py`
  - **Archive**: identify beliefs/notes not referenced in N days, mark for archive with grace period
  - **Deduplicate**: find notes/beliefs with cosine similarity >= threshold, merge
  - **Distill**: create summary notes from clusters of related notes
  - All actions logged to audit trail
  - No silent deletion — archived items remain queryable
- [ ] Write tests for archive, dedup, and distill logic

### 2.4 Belief Status Automation

- [ ] Wire automatic status transitions into scheduled runs:
  - `proposed -> active` when confidence >= activation_threshold and no contradictions
  - `challenged -> deprecated` when counterevidence dominates
  - `deprecated -> archived` per curator policy
- [ ] Write tests for automatic lifecycle progression

### 2.5 User Feedback Signals

- [ ] Implement CLI commands for user feedback:
  - `confirm <belief_id>` — emit `signal:belief_confirmed`, boost confidence
  - `refute <belief_id>` — emit `signal:belief_refuted`, reduce confidence
  - `trust <source_id> <level>` — emit `signal:source_trust_updated`
- [ ] Wire feedback signals into agent processing
- [ ] Write tests for feedback-driven confidence changes

### 2.6 Reports

- [ ] Implement report generation (CLI command or scheduled output):
  - Summary of new beliefs since last report
  - Active contradictions
  - Beliefs approaching decay threshold
  - Recently archived items
- [ ] Add `report` CLI command
- [ ] Write tests for report content accuracy

### 2.7 Snapshot & Restore

- [ ] Implement `snapshot` CLI command — full SQLite database backup with timestamp
- [ ] Implement `restore` CLI command — restore from a named snapshot
- [ ] Verify round-trip: snapshot, mutate, restore, verify original state
- [ ] Write tests for snapshot/restore integrity

### 2.8 Anti-Rot Policies

- [ ] Enforce mandatory decay — no belief exempt from time-based confidence reduction (unless decay_model=none is explicitly set)
- [ ] Enforce mandatory archive review — curator must evaluate all cold items each cycle
- [ ] Enforce mandatory duplicate detection — curator must run dedup each cycle
- [ ] Enforce no silent deletion — all removals logged, archived items remain in DB
- [ ] Write tests verifying each policy is enforced

### 2.9 Security & Integrity Hardening

- [ ] Verify foreign keys are enforced across all tables
- [ ] Verify content_hash is checked on note retrieval (tamper detection)
- [ ] Verify edge referential integrity (no dangling edges)
- [ ] Verify LLM output (if used) never directly mutates beliefs — always mediated by services
- [ ] Write integrity tests

### 2.10 Phase 2 Validation

- [ ] Long-run integration test: simulate multi-day lifecycle with notes, beliefs, decay, archival
- [ ] Verify scheduler runs all agents in correct order without errors
- [ ] Verify snapshot/restore preserves full system state
- [ ] Verify audit log captures every mutation across the entire lifecycle
- [ ] Verify no in-memory-only state, no silent deletions, no uncited beliefs

---

## Completion Criteria

All three phases are complete when:

- [ ] Notes persist, are searchable via FTS and vector similarity, and are immutable
- [ ] Beliefs have full lifecycle management with deterministic confidence scoring
- [ ] Contradictions are detected and surfaced explicitly
- [ ] The ask pipeline returns only evidence-grounded, cited answers
- [ ] Background agents run on schedule and maintain system health
- [ ] Every mutation is auditable and reversible
- [ ] Snapshot/restore provides full backup capability
- [ ] All tests pass
