# Second Brain Usage Guide

## Installation

**Requirements:** Python 3.12 or later.

```bash
# Clone the repository
git clone <repo-url>
cd second_brain

# Install with pip
pip install -e .

# Or with uv (recommended)
uv sync
```

After installation the `sb` command is available in your terminal.

Verify with:

```bash
sb --help
```

### Optional: Vector Search

Second Brain uses `sentence-transformers` for semantic vector search. This is included in the default dependencies. If it fails to load (e.g. on a constrained system), the application falls back to keyword-only (FTS5) search with a logged warning. No action is required -- everything works without it, you just lose semantic similarity.

---

## Database

All data is stored in a single SQLite file.

| Method | Example |
|--------|---------|
| Default location | `~/.second_brain/brain.db` (created automatically) |
| `--db` flag | `sb --db /path/to/my.db add "note"` |
| Environment variable | `SB_DB_PATH=/path/to/my.db sb add "note"` |

The database directory is created automatically if it does not exist. Schema migrations run on first connection.

---

## Adding Notes

### From an argument

```bash
sb add "Rust's ownership model prevents data races at compile time #rust #memory-safety"
```

### From stdin

```bash
echo "Some content" | sb add
```

```bash
# Multi-line from a file
sb add < my_notes.txt
```

### With options

```bash
sb add "def hello(): pass" --type code --source file -t python -t snippets
```

| Option | Short | Values | Default |
|--------|-------|--------|---------|
| `--type` | | `text`, `markdown`, `pdf`, `transcript`, `code` | `text` |
| `--source` | | `user`, `file`, `url`, `clipboard` | `user` |
| `--tags` | `-t` | Any string (repeatable) | none |

### Automatic extraction

Tags and entities are extracted automatically from content in addition to any you provide manually:

- **Tags**: words prefixed with `#` (e.g. `#python`, `#machine-learning`)
- **Entities**: words prefixed with `@` (e.g. `@numpy`, `@john.smith`)

Tags are normalized to lowercase and capped at 100 characters.

### Example output

```
Note created: a1b2c3d4-5678-9abc-def0-123456789abc
Tags: rust, memory-safety
```

---

## Searching Notes

### Keyword search (FTS5)

```bash
sb search "rust ownership"
```

Results show a snippet of each matching note with its UUID and tags:

```
[a1b2c3d4-...] Rust's ownership model prevents data races at compile time
  tags: rust, memory-safety
```

Limit results with `-n`:

```bash
sb search "python" -n 5
```

The search uses SQLite FTS5 under the hood. Standard keywords work; malformed queries (unbalanced quotes, bare operators) return empty results gracefully rather than crashing.

### Viewing a full note

```bash
sb show a1b2c3d4-5678-9abc-def0-123456789abc
```

Output includes the note ID, creation timestamp, content type, SHA-256 hash, source information, tags, entities, and full content.

---

## Asking Questions

The `ask` command combines keyword search, vector similarity (if available), and belief retrieval to answer your question using only stored evidence.

```bash
sb ask "What are the tradeoffs of Rust vs Python for concurrency?"
```

### What happens

1. FTS5 keyword search against your notes
2. Vector similarity search (if embeddings are available)
3. Results are merged and deduplicated
4. Related beliefs are retrieved via the edge graph
5. Evidence and beliefs are displayed with citations

### Example output

```
=== Evidence Notes ===
  [1] (a1b2c3d4-...) Rust's ownership model prevents data races at compile time
      tags: rust, memory-safety
  [2] (e5f6a7b8-...) Python's GIL prevents true parallelism in CPU-bound threads
      tags: python, concurrency

=== Related Beliefs ===
  - [active] (confidence: 0.70) Multiple notes discuss concurrency (2 sources)

=== Answer ===
Based on 2 evidence note(s):
  [1] Rust's ownership model prevents data races at compile time
  [2] Python's GIL prevents true parallelism in CPU-bound threads

Related beliefs (1):
  - Multiple notes discuss concurrency (2 sources) (confidence: 0.70)
```

Adjust how many notes to consider with `--top-k`:

```bash
sb ask "machine learning basics" -k 10
```

---

## Beliefs

Beliefs are claims derived from your notes. They have a lifecycle, a confidence score, and explicit evidence links.

### How beliefs are created

Beliefs are proposed automatically when you run agents (`sb run`). The **SynthesisAgent** groups notes that share tags or entities and creates beliefs like:

> "Multiple notes discuss python (5 sources)"

Each belief starts as `proposed` with a confidence score based on the number of supporting notes.

### Belief statuses

| Status | Meaning |
|--------|---------|
| `proposed` | Newly derived, awaiting evaluation |
| `active` | Confidence meets threshold, no contradictions |
| `challenged` | A contradiction has been detected |
| `deprecated` | Counterevidence dominates |
| `archived` | Cold, no longer relevant |

### Automatic transitions

When you run `sb run`, the lifecycle rules evaluate every belief:

- **proposed -> active**: confidence >= 0.6 AND no contradictions detected
- **challenged -> deprecated**: confidence < 0.2
- **deprecated -> archived**: not updated in 90+ days (curator policy)
- **active -> challenged**: contradiction detected by the ChallengerAgent

### Confidence formula

```
confidence = clamp(
    (0.5 + 0.1 * supports - 0.1 * contradicts) * decay_factor,
    0.0, 1.0
)
```

- Each incoming `supports` edge adds 0.1
- Each incoming `contradicts` edge subtracts 0.1
- Time decay (exponential, 30-day half-life) reduces confidence over time
- Beliefs with `decay_model=none` do not decay

### Manual feedback

Boost a belief you agree with:

```bash
sb confirm <BELIEF_ID>
```

Push back on a belief you disagree with:

```bash
sb refute <BELIEF_ID>
```

Each confirm/refute adjusts confidence by +/- 0.1 and emits a signal that agents can react to.

---

## Source Trust

Every note has a source. You can adjust how much you trust a source:

```bash
sb trust <SOURCE_ID> trusted
sb trust <SOURCE_ID> unknown
sb trust <SOURCE_ID> user
```

| Level | Meaning |
|-------|---------|
| `user` | Directly authored by you |
| `trusted` | From a verified external source |
| `unknown` | Default; unverified origin |

---

## Running Agents

The `sb run` command executes a single scheduler tick that runs all agents in order:

```bash
sb run
```

### Execution order

1. **CuratorAgent** -- archives beliefs that have been deprecated for 90+ days, deduplicates beliefs with >= 95% cosine similarity, and distills notes that share tags (5+ notes per tag get a summary)
2. **Lifecycle rules** -- automatically transitions beliefs based on confidence thresholds and contradictions
3. **ChallengerAgent** -- processes `belief_proposed` signals, runs contradiction detection (negation and opposing predicates), creates `contradicts` edges, and challenges active beliefs
4. **SynthesisAgent** -- processes `new_note` signals, groups notes by tag/entity, and proposes new beliefs with `supports` edges

### Example output

```
  curator: {'archived': 2, 'deduplicated': 0, 'distilled': 1}
  lifecycle: {'activated': 3, 'deprecated': 1}
  challenger: [UUID('...')]
  synthesis: [UUID('...'), UUID('...')]
```

### Typical workflow

Run agents after adding new notes to keep your knowledge base current:

```bash
sb add "New research finding about X #topic"
sb add "Another data point about X #topic"
sb run
sb report
```

---

## Reports

Generate a status report of your entire knowledge base:

```bash
sb report
```

### Example output

```
=== Knowledge Base Report ===
Total notes: 47
Beliefs [proposed]: 3
Beliefs [active]: 12
Beliefs [challenged]: 1
Beliefs [deprecated]: 2
Beliefs [archived]: 5

--- Active Contradictions ---
  Python is fast (confidence: 0.30, contradictions: 1)

--- Low Confidence Beliefs ---
  Python is easy to deploy (confidence: 0.20)

--- Recently Archived ---
  Old claim about deprecated library
```

---

## Backups

### Create a snapshot

```bash
# Auto-named with timestamp
sb snapshot

# Custom path
sb snapshot /backups/brain_2026-02-10.db
```

Output: `Snapshot saved: /home/user/.second_brain/brain_snapshot_20260210_143000.db`

### Restore from a snapshot

```bash
sb restore /backups/brain_2026-02-10.db
```

Before overwriting, the current database is automatically backed up to `brain_pre_restore_<timestamp>.db` so you can recover if the restore was a mistake.

---

## Workflows

### Building a knowledge base from scratch

```bash
# 1. Add notes from various sources
sb add "Key insight about topic A #topicA"
sb add "Supporting detail about topic A #topicA @source1"
sb add "Contradicting view on topic A #topicA"
sb add "Observation about topic B #topicB"

# 2. Run agents to derive beliefs and detect contradictions
sb run

# 3. Review what was derived
sb report

# 4. Provide feedback on beliefs you agree/disagree with
sb confirm <BELIEF_ID>
sb refute <BELIEF_ID>

# 5. Run again to process your feedback
sb run
```

### Importing from files

```bash
# Pipe file content
sb add < research_paper.txt --type text --source file -t research

# From clipboard (macOS)
pbpaste | sb add --source clipboard
```

### Regular maintenance

```bash
# Run agents periodically to keep beliefs current
sb run

# Check system health
sb report

# Back up before any major changes
sb snapshot
```

### Investigating a topic

```bash
# Search for what you know
sb search "machine learning"

# Ask a structured question
sb ask "What are the key challenges in deploying ML models?"

# Drill into a specific note
sb show <NOTE_ID>
```

---

## How It Works Internally

### Data flow

```
User input (sb add)
  → IngestionAgent creates Source + Note
  → Tags/entities extracted via regex
  → Embedding computed (if available)
  → signal:new_note emitted

Agent tick (sb run)
  → CuratorAgent: archive, deduplicate, distill
  → Lifecycle: auto-transition beliefs by confidence
  → ChallengerAgent: detect contradictions, challenge beliefs
  → SynthesisAgent: group notes, propose beliefs

User query (sb ask)
  → FTS5 keyword search
  → Vector similarity search
  → Merge results, retrieve linked beliefs
  → Display evidence + beliefs
```

### Key concepts

- **Notes** are immutable once created. They are the raw evidence.
- **Beliefs** are derived claims with managed lifecycles. They can be proposed, activated, challenged, deprecated, and archived.
- **Edges** link entities together (note supports belief, belief contradicts belief, note derived_from note, etc.).
- **Signals** are internal events that agents subscribe to. They drive the reactive pipeline.
- **Audit log** records every mutation for full traceability.

### Contradiction detection

The ChallengerAgent uses two heuristics:

1. **Negation**: "X is Y" vs "X is not Y" (or "X isn't Y")
2. **Opposing predicates**: Claims that share subject words but use opposing terms (fast/slow, good/bad, safe/unsafe, increase/decrease, etc.)

When a contradiction is found, a `contradicts` edge is created and the conflicting belief is moved to `challenged` status.

### Confidence decay

Beliefs use exponential decay with a 30-day half-life by default. A belief that was last updated 30 days ago has its confidence multiplied by 0.5. At 60 days, 0.25. This ensures stale beliefs naturally lose influence.

---

## Troubleshooting

### "No results found" on search

FTS5 searches require matching terms. Try shorter or broader queries. Special characters and FTS5 operators (AND, OR, NOT) are handled gracefully -- malformed queries return empty results rather than errors.

### Vector search not working

Check if `sentence-transformers` is installed:

```bash
python -c "import sentence_transformers; print('OK')"
```

If not installed, the system falls back to FTS-only search. A warning is logged at startup.

### Database location

The default database is at `~/.second_brain/brain.db`. Override with:

```bash
sb --db /custom/path.db <command>
# or
export SB_DB_PATH=/custom/path.db
```
