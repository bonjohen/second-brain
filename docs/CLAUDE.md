# Second Brain - Project Guide

## Project Overview
A local, persistent cognitive substrate built in Python. Captures user-authored information, stores it in structured queryable form, derives and manages belief objects with confidence/evidence/lifecycle, answers questions using only stored evidence, and evolves knowledge via deterministic background processes.

## Tech Stack
- **Language:** Python 3.11+
- **Storage:** SQLite (single source of truth) + FTS5 for full-text search
- **Vector:** Local vector index (derived/rebuildable state)
- **CLI:** Click or Typer
- **Testing:** pytest
- **Migrations:** Custom SQLite migration system

## Architecture
- `second_brain/core/` — Models and domain services (notes, beliefs, edges, audit, signals)
- `second_brain/core/rules/` — Deterministic rules (confidence, decay, contradictions)
- `second_brain/agents/` — Autonomous agents (ingestion, synthesis, challenger, curator)
- `second_brain/storage/` — SQLite, migrations, vector index
- `second_brain/runtime/` — Dispatcher and scheduler
- `second_brain/cli/` — CLI entry point
- `tests/` — All tests

## Design Principles
- **Determinism:** Identical inputs produce identical state transitions
- **Traceability:** Every belief, answer, and mutation links to evidence
- **Challengeability:** Contradictions are explicit; unresolved states are valid
- **Persistence:** All state survives restarts; migrations are explicit
- **Local-first:** No implicit network access

## Key Domain Objects
- **Note** — Immutable captured content with hash, tags, entities
- **Source** — Origin metadata with trust labels
- **Belief** — Claims with confidence scores and lifecycle (proposed → active → challenged → deprecated → archived)
- **Edge** — Typed relationships (supports, contradicts, derived_from, related)
- **Signal** — Event queue entries driving agent reactions

## Trust Rules
- User notes are assertions, not truth
- System inferences are provisional
- Missing data is never inferred
- No belief may exist without evidence
- LLM output never directly mutates beliefs

## Commands
```bash
# Run tests
pytest tests/

# Run CLI
python -m second_brain.cli.main

# Run migrations
python -m second_brain.storage.migrations
```

## Implementation Phases
- **Phase 0 (Capture):** SQLite schema, Note/Source services, CLI add/search/show, FTS, persistence tests
- **Phase 1 (Reasoning):** Belief/Edge services, confidence/decay rules, challenger, vector embeddings, ask pipeline, synthesis+challenger agents
- **Phase 2 (Proactive):** Scheduler/dispatcher, curator agent, archive/merge/distill, reports, snapshot/restore, long-run integrity tests
