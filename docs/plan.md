# Second Brain — Implementation Plan

## Phase 0: Project Bootstrap — COMPLETE

- [x] **0.1** Init project scaffolding — pyproject.toml, .gitignore, git init, directory tree
- [x] **0.2** SQLite schema + migration system — 5 core tables + audit_log, FTS5, migration runner
- [x] **0.3** Core models — Pydantic models for Note, Source, Belief, Edge, Signal, AuditEntry
- [x] **0.4** Storage layer — storage/sqlite.py connection manager, WAL mode, FK enforcement
- [x] **0.5** Note + Source services — CRUD, immutability, content hashing (sha256)
- [x] **0.6** Signal service — services/signals.py emit/consume pattern
- [x] **0.7** Audit service — services/audit.py append-only mutation logging
- [x] **0.8** IngestionAgent (basic) — Source + Note creation, tag/entity extraction, signal emission
- [x] **0.9** CLI: add / search / show / list — Typer CLI commands
- [x] **0.10** Tests for Phase 0 — 20/20 passing

## Phase 1: Reasoning — COMPLETE

- [x] **1.1** Edge service — create/query typed edges with referential integrity checks
- [x] **1.2** Belief service — full lifecycle (proposed→active→challenged→deprecated→archived) + transition validation
- [x] **1.3** Confidence rules — deterministic formula: clamp((Σ supports - Σ counters) * decay, 0, 1)
- [x] **1.4** Decay rules — exponential decay with 30-day half-life
- [x] **1.5** Contradiction rules — exact negation detection + opposing predicates
- [x] **1.6** Vector storage — basic hash embeddings (sentence-transformers optional), cosine similarity, rebuildable
- [x] **1.7** SynthesisAgent — note grouping by tags/entities, belief generation, supports edges
- [x] **1.8** ChallengerAgent — belief-vs-belief and note-vs-belief contradiction detection
- [x] **1.9** Ask pipeline — FTS + vector hybrid search, evidence assembly, template-based synthesis
- [x] **1.10** CLI: ask / beliefs / confirm / refute commands
- [x] **1.11** Tests for Phase 1 — 26/26 passing (46 total)

## Phase 2: Proactive — COMPLETE

- [x] **2.1** Dispatcher — signal consumption and agent routing with configurable routes
- [x] **2.2** Scheduler — periodic tick (Curator → Challenger → Synthesis → Dispatch)
- [x] **2.3** CuratorAgent — archive cold beliefs, detect duplicates, grace period enforcement
- [x] **2.4** Archive/merge/distill policies — 90-day cold threshold, 7-day grace, 0.92 similarity threshold
- [x] **2.5** Snapshot/restore — SQLite backup API, pre-restore safety backup
- [x] **2.6** Reports — health report with counts by entity type, belief status breakdown, contradiction count
- [x] **2.7** CLI: status / snapshot / restore / report / process commands
- [x] **2.8** End-to-end tests — full lifecycle + contradiction lifecycle (57/57 passing)

## Phase 3: Integrations — COMPLETE

- [x] **3.1** Telegram bot — message ingestion, all commands (/ask, /search, /beliefs, /confirm, /refute, /status, /process)
- [x] **3.2** Telegram tests — 14/14 passing (71 total)

---

## Tech Choices
- **Typer** — CLI framework
- **Pydantic v2** — model validation
- **Rich** — CLI output (tables, panels)
- **sqlite3** (stdlib) — storage with WAL, FK enforcement
- **sentence-transformers** — optional local embeddings (falls back to hash-based)
- **python-telegram-bot** — Telegram bot integration (optional)
- **uv** — package management

## File Inventory

```
second_brain/
├── __init__.py
├── core/
│   ├── models.py              # All domain objects (Note, Source, Belief, Edge, Signal, AuditEntry)
│   ├── services/
│   │   ├── notes.py           # Note + Source CRUD, FTS search
│   │   ├── beliefs.py         # Belief lifecycle management
│   │   ├── edges.py           # Graph edge operations
│   │   ├── signals.py         # Event queue
│   │   ├── audit.py           # Append-only audit log
│   │   ├── ask.py             # Ask pipeline (hybrid search + evidence assembly)
│   │   └── reports.py         # Health report generation
│   └── rules/
│       ├── confidence.py      # Confidence formula
│       ├── decay.py           # Exponential decay
│       └── contradictions.py  # Contradiction detection heuristics
├── agents/
│   ├── ingestion.py           # IngestionAgent
│   ├── synthesis.py           # SynthesisAgent
│   ├── challenger.py          # ChallengerAgent
│   └── curator.py             # CuratorAgent
├── storage/
│   ├── sqlite.py              # Database connection manager
│   ├── vector.py              # Vector embeddings + cosine similarity
│   ├── snapshot.py            # Backup/restore
│   └── migrations/
│       ├── runner.py          # Migration runner
│       └── 001_initial_schema.sql
├── runtime/
│   ├── dispatcher.py          # Signal → agent routing
│   └── scheduler.py           # Periodic proactive pipeline
├── integrations/
│   └── telegram.py            # Telegram bot (message → note, commands)
├── cli/
│   └── main.py                # All CLI commands (including `brain telegram`)
└── tests/
    ├── test_phase0.py         # 20 tests
    ├── test_phase1.py         # 26 tests
    ├── test_phase2.py         # 11 tests
    └── test_telegram.py       # 14 tests
```
