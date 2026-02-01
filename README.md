# Second Brain

A local, persistent cognitive substrate that captures information, derives structured beliefs with confidence tracking, detects contradictions, and answers questions grounded in stored evidence.

## What it does

- **Captures** notes from the CLI with automatic tag and entity extraction
- **Derives beliefs** from patterns across notes, each with a confidence score and lifecycle
- **Detects contradictions** between beliefs and incoming evidence
- **Answers questions** using hybrid full-text + vector search, citing only stored evidence
- **Self-maintains** via background agents that archive stale content, merge duplicates, and flag conflicts
- **Audits everything** -- every mutation is logged, every belief traces back to evidence, and the full database can be snapshotted and restored

## Quick start

Requires Python 3.11+.

```bash
# Clone and install
git clone <repo-url> && cd beta_brain
uv venv .venv && source .venv/Scripts/activate   # or .venv/bin/activate on Linux/Mac
uv pip install -e ".[dev]"

# Add some notes
brain add "Python was created by Guido van Rossum in 1991"
brain add "Python is widely used in #datascience and #machinelearning"
brain add "Rust is gaining popularity for systems programming"

# Search and query
brain search "Python"
brain ask "What do I know about Python?"
brain list

# View a specific note (supports ID prefix matching)
brain show a3f8

# Run a proactive cycle (synthesize beliefs, detect contradictions)
brain process

# Check system state
brain status
brain beliefs
brain report
```

## CLI commands

| Command | Description |
|---------|-------------|
| `brain add <text>` | Add a note (supports `--type`, `--tags`, and piped stdin) |
| `brain search <query>` | Full-text search across notes |
| `brain ask <question>` | Evidence-grounded Q&A with citations |
| `brain show <id>` | Show full note detail (prefix match supported) |
| `brain list` | List recent notes |
| `brain beliefs` | List all beliefs (filter with `--status active`) |
| `brain confirm <id>` | Boost a belief's confidence (+0.2) |
| `brain refute <id>` | Reduce a belief's confidence (-0.3) and challenge it |
| `brain process` | Run one proactive cycle (synthesis, challenge, curation) |
| `brain status` | System health overview |
| `brain report` | Detailed health report |
| `brain snapshot` | Create a database backup |
| `brain restore [path]` | Restore from a snapshot (latest if no path given) |

## Architecture

```
second_brain/
├── core/
│   ├── models.py              # Domain objects: Note, Source, Belief, Edge, Signal
│   ├── services/              # CRUD and business logic
│   │   ├── notes.py           # Note + Source persistence, FTS search
│   │   ├── beliefs.py         # Belief lifecycle state machine
│   │   ├── edges.py           # Typed graph relationships
│   │   ├── signals.py         # Event queue (emit/consume)
│   │   ├── audit.py           # Append-only audit log
│   │   ├── ask.py             # Ask pipeline (hybrid search + evidence assembly)
│   │   └── reports.py         # Health report generation
│   └── rules/                 # Deterministic logic
│       ├── confidence.py      # Confidence = clamp((supports - counters) * decay)
│       ├── decay.py           # Exponential decay (30-day half-life)
│       └── contradictions.py  # Negation and opposing-predicate detection
├── agents/
│   ├── ingestion.py           # Captures input → Note + Source + signal
│   ├── synthesis.py           # Groups notes → proposes beliefs
│   ├── challenger.py          # Detects contradictions → challenges beliefs
│   └── curator.py             # Archives stale, detects duplicates
├── storage/
│   ├── sqlite.py              # Connection manager (WAL, FK enforcement)
│   ├── vector.py              # Embeddings + cosine similarity search
│   ├── snapshot.py            # Backup/restore via SQLite backup API
│   └── migrations/            # Schema versioning
├── runtime/
│   ├── dispatcher.py          # Signal → agent routing
│   └── scheduler.py           # Periodic proactive pipeline
└── cli/
    └── main.py                # All CLI commands
```

## Core concepts

### Notes
Immutable captures of information. Each note has a content hash, extracted tags (`#hashtags`), extracted entities (Proper Case names), and a link to its source. Notes are never modified after creation.

### Beliefs
Derived claims with a confidence score and a lifecycle:

```
proposed → active ↔ challenged → deprecated → archived
```

Every transition is validated, logged, and reversible. Beliefs only exist when backed by evidence (notes linked via edges).

### Edges
Typed graph relationships connecting notes, beliefs, and sources:
- **supports** -- evidence for a belief
- **contradicts** -- evidence against a belief
- **derived_from** -- provenance link
- **related** -- curator-detected similarity

### Confidence
Deterministic formula combining supporting evidence, counter-evidence, and time decay:

```
confidence = clamp((sum(support_weights) - sum(counter_weights)) * decay_factor, 0.0, 1.0)
```

Decay uses an exponential model with a 30-day half-life. Beliefs that aren't referenced lose confidence over time.

### Signals
An internal event queue that coordinates agents. Adding a note emits `new_note`, which triggers synthesis and challenge checks. User actions like `confirm` and `refute` emit their own signals.

## Design principles

- **Determinism** -- identical inputs produce identical state transitions
- **Traceability** -- every belief and answer links back to evidence
- **Challengeability** -- contradictions are explicit; unresolved states are valid
- **Persistence** -- all state is in SQLite; nothing is memory-only
- **Local-first** -- no network calls unless you explicitly opt in

## Storage

SQLite is the single source of truth. The schema includes:
- `notes`, `sources`, `beliefs`, `edges`, `signals`, `audit_log` tables
- FTS5 virtual table for full-text search
- Triggers to keep the FTS index in sync
- Foreign key constraints enforced
- WAL journal mode for concurrent reads

The vector index (used for semantic search) is derived state and can be rebuilt from notes at any time.

## Telegram bot

Use the brain from Telegram -- any message you send is captured as a note, and slash commands give you full access to search, ask, beliefs, and more.

### Setup

1. Talk to [@BotFather](https://t.me/BotFather) on Telegram and create a new bot. Copy the token.
2. Install the telegram extra:
   ```bash
   uv pip install -e ".[telegram]"
   ```
3. Start the bot:
   ```bash
   # Via environment variable
   export TELEGRAM_BOT_TOKEN="your-token-here"
   brain telegram

   # Or inline
   brain telegram --token "your-token-here"
   ```

### Bot commands

| Command | Description |
|---------|-------------|
| *(any message)* | Captured as a note with auto-extracted tags and entities |
| `/ask <query>` | Evidence-grounded Q&A |
| `/search <query>` | Full-text search |
| `/beliefs [status]` | List beliefs (optional status filter) |
| `/confirm <id>` | Confirm a belief (+0.2 confidence) |
| `/refute <id>` | Refute a belief (-0.3 confidence) |
| `/status` | System health overview |
| `/process` | Run a proactive cycle |
| `/help` | Show available commands |

The bot shares the same SQLite database as the CLI, so notes added from either interface are immediately available in both.

## Optional: semantic search

Install the `vectors` extra for sentence-transformer-based embeddings:

```bash
uv pip install -e ".[vectors]"
```

Without it, the system falls back to a basic hash-based embedding that still supports cosine similarity search.

## Development

```bash
# Install with dev dependencies
uv pip install -e ".[dev]"

# Run tests (71 tests across all phases)
pytest tests/ -v

# Run a specific phase
pytest tests/test_phase0.py -v
pytest tests/test_phase1.py -v
pytest tests/test_phase2.py -v
pytest tests/test_telegram.py -v

# Run with coverage
pytest tests/ --cov=second_brain
```

## License

Unlicensed. Private project.
