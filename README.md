# Second Brain

A local, persistent cognitive substrate built in Python. Second Brain captures information, stores it in structured and queryable form, derives managed **belief objects** with confidence and evidence tracking, and evolves its knowledge through deterministic background processes.

## What It Does

- **Captures** user-authored notes from multiple sources (text, markdown, PDF, transcripts, code)
- **Structures** information with tags, entities, and full-text search
- **Derives beliefs** from stored evidence with explicit confidence scores
- **Detects contradictions** and manages belief lifecycles (proposed, active, challenged, deprecated, archived)
- **Answers questions** grounded only in stored evidence with verifiable citations
- **Self-maintains** via scheduled curation, decay, deduplication, and archival

## Core Principles

- **Determinism** -- identical inputs produce identical state transitions
- **Traceability** -- every belief, answer, and mutation links back to evidence
- **Challengeability** -- contradictions are explicit; unresolved states are valid
- **Persistence** -- all state survives restarts; no in-memory-only state
- **Local-first** -- no implicit network access

## Architecture

```
second_brain/
├── core/           # Data models, services (notes, beliefs, edges, audit, signals), rules
├── agents/         # Ingestion, Synthesis, Challenger, Curator
├── storage/        # SQLite (source of truth), migrations, vector index
├── runtime/        # Dispatcher and scheduler
├── cli/            # CLI entrypoint
├── docs/           # Design documents
└── tests/
```

### Key Components

| Component | Role |
|-----------|------|
| **IngestionAgent** | Processes new input into Notes + Sources, extracts tags/entities, computes embeddings |
| **SynthesisAgent** | Groups related notes and proposes new Beliefs with supporting edges |
| **ChallengerAgent** | Detects contradictions, challenges beliefs, adjusts confidence |
| **CuratorAgent** | Archives cold data, merges duplicates, generates summaries |

### Storage

- **SQLite** is the single source of truth
- Graph relationships are stored via an `edges` table
- Vector index is derived state (fully rebuildable)

## Pipelines

**Add** -- Ingest a note via CLI, persist Note + Source, compute embedding, emit signal.

**Ask** -- Keyword + vector search, retrieve active beliefs, assemble evidence, synthesize a cited answer.

**Proactive** -- Scheduled tick runs Curator, Challenger, and Synthesis agents to evolve the knowledge base.

## Implementation Phases

| Phase | Focus | Outcome |
|-------|-------|---------|
| **0 -- Capture** | SQLite schema, Note/Source services, CLI add/search/show, FTS | Notes persist, searchable, audited |
| **1 -- Reasoning** | Belief/Edge services, confidence/decay rules, vector embeddings, ask pipeline | Beliefs tracked, contradictions handled, answers grounded |
| **2 -- Proactive** | Scheduler, CuratorAgent, archive/merge/distill, snapshot/restore | Self-maintaining system with full auditability |

## Design Document

See [docs/PDR.MD](docs/PDR.MD) for the full executable technical design document including object schemas, lifecycle rules, agent specifications, and deterministic confidence formulas.
