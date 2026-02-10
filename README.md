# Second Brain

A local, persistent cognitive substrate built in Python. Second Brain captures information, stores it in structured and queryable form, derives managed **belief objects** with confidence and evidence tracking, and evolves its knowledge through deterministic background processes.

## What It Does

- **Captures** user-authored notes from multiple sources (text, markdown, PDF, transcripts, code)
- **Structures** information with tags, entities, full-text search, and vector similarity
- **Derives beliefs** from stored evidence with explicit confidence scores
- **Detects contradictions** and manages belief lifecycles (proposed, active, challenged, deprecated, archived)
- **Answers questions** grounded only in stored evidence with verifiable citations
- **Self-maintains** via scheduled curation, decay, deduplication, and archival

## Quick Start

```bash
# Install (requires Python 3.12+)
pip install -e .
# or with uv:
uv sync

# Add your first note
sb add "Python's GIL prevents true parallelism in CPU-bound threads #python #concurrency"

# Search your notes
sb search "python concurrency"

# Run agents to derive beliefs and detect contradictions
sb run

# Ask a question
sb ask "What do I know about Python concurrency?"

# See a full report
sb report
```

## Core Principles

- **Determinism** -- identical inputs produce identical state transitions
- **Traceability** -- every belief, answer, and mutation links back to evidence
- **Challengeability** -- contradictions are explicit; unresolved states are valid
- **Persistence** -- all state survives restarts; no in-memory-only state
- **Local-first** -- no implicit network access; all data stays on your machine

## Architecture

```
second_brain/
├── core/           # Data models, services (notes, beliefs, edges, audit, signals), rules
├── agents/         # Ingestion, Synthesis, Challenger, Curator
├── storage/        # SQLite (source of truth), migrations, vector index
├── runtime/        # Dispatcher and scheduler
├── cli/            # CLI entrypoint (sb command)
└── tests/          # 225 tests covering all layers
```

### Key Components

| Component | Role |
|-----------|------|
| **IngestionAgent** | Processes new input into Notes + Sources, extracts tags/entities, computes embeddings |
| **SynthesisAgent** | Groups related notes and proposes new Beliefs with supporting edges |
| **ChallengerAgent** | Detects contradictions, challenges beliefs, adjusts confidence |
| **CuratorAgent** | Archives cold data, merges duplicates, generates summaries |

### Storage

- **SQLite** is the single source of truth (default: `~/.second_brain/brain.db`)
- **FTS5** provides full-text search across notes, tags, and entities
- **Vector index** enables semantic similarity via sentence-transformers (optional, graceful fallback)
- **Edges table** implements a polymorphic graph for relationships between notes, beliefs, and sources
- **Append-only audit log** records every mutation with before/after state

### Belief Lifecycle

```
proposed ──→ active ──→ challenged ──→ deprecated ──→ archived
               ↑            │
               └────────────┘
```

Beliefs are derived from evidence, scored with a confidence formula that accounts for supporting/contradicting edges and time decay, and automatically transitioned based on deterministic rules.

## CLI Commands

| Command | Description |
|---------|-------------|
| `sb add [CONTENT]` | Add a note (reads stdin if no argument) |
| `sb search QUERY` | Full-text search notes |
| `sb show NOTE_ID` | Display full note details |
| `sb ask QUESTION` | Query with evidence and beliefs |
| `sb confirm BELIEF_ID` | Boost a belief's confidence (+0.1) |
| `sb refute BELIEF_ID` | Reduce a belief's confidence (-0.1) |
| `sb trust SOURCE_ID LEVEL` | Set source trust (user/trusted/unknown) |
| `sb report` | Knowledge base status report |
| `sb run` | Run all agents (curator, lifecycle, challenger, synthesis) |
| `sb snapshot [PATH]` | Create a database backup |
| `sb restore PATH` | Restore from a backup |

Run `sb --help` or `sb <command> --help` for full option details.

## Configuration

| Setting | Method | Default |
|---------|--------|---------|
| Database path | `--db PATH` or `SB_DB_PATH` env var | `~/.second_brain/brain.db` |
| Vector search | Automatic if `sentence-transformers` installed | FTS-only fallback |

## Documentation

- **[Usage Guide](docs/USAGE.md)** -- detailed walkthrough of all commands and workflows
- **[Design Document](docs/PDR.MD)** -- full technical design with schemas, rules, and agent specs

## Development

```bash
# Install with dev dependencies
uv sync

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=second_brain

# Lint
uv run ruff check .
```

## License

This project is for personal use.
