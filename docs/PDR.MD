No.
The previous version was close, but it still left several implementation decisions implicit (schemas, deterministic rules, execution order, and agent boundaries). Below is a **fully sufficient, handoff-ready technical design document** whose explicit purpose is to allow **another coding-capable AI to build the system without asking clarifying questions**.

---

# SECOND BRAIN — EXECUTABLE TECHNICAL DESIGN DOCUMENT

*(Local, personal-scale, Python)*

---

## 1. Purpose & Scope

### 1.1 System definition

This system is a **local, persistent cognitive substrate** that:

* Captures user-authored information.
* Stores it in structured, queryable form.
* Derives and manages **belief objects** with confidence, evidence, and lifecycle.
* Answers questions using only stored evidence.
* Evolves its knowledge via deterministic background processes.

### 1.2 Problems solved

* Long-term memory beyond human recall.
* Structured synthesis from raw notes.
* Explicit belief tracking with contradiction handling.
* Consistent reasoning across time with auditability.

---

## 2. Core Principles

### 2.1 Design axioms

* **Determinism**: identical inputs produce identical state transitions.
* **Traceability**: every belief, answer, and mutation links to evidence.
* **Challengeability**: contradictions are explicit and unresolved states are valid.
* **Persistence**: all state survives restarts; migrations are explicit.
* **Local-first**: no implicit network access.

### 2.2 User assumptions

* Technically sophisticated.
* CLI-first workflow.
* Accepts explicit models over implicit AI behavior.

### 2.3 Trust rules

* User notes are *assertions*, not truth.
* System inferences are *provisional*.
* Missing data is never inferred.
* No belief may exist without evidence.

---

## 3. Conceptual Model (Authoritative)

### 3.1 Objects (required)

#### Note

```
note_id: UUID
created_at: timestamp
content: text | blob
content_type: enum(text, markdown, pdf, transcript, code)
source_id: UUID
tags: string[]
entities: string[]
content_hash: sha256
```

#### Source

```
source_id: UUID
kind: enum(user, file, url, clipboard)
locator: string
captured_at: timestamp
trust_label: enum(user, trusted, unknown)
```

#### Belief

```
belief_id: UUID
claim_text: string
status: enum(proposed, active, challenged, deprecated, archived)
confidence: float [0.0–1.0]
created_at: timestamp
updated_at: timestamp
decay_model: enum(exponential, none)
scope: json
derived_from_agent: string
```

#### Edge

```
edge_id: UUID
from_type: enum(note, belief, source)
from_id: UUID
rel_type: enum(supports, contradicts, derived_from, related)
to_type: enum(note, belief, source)
to_id: UUID
```

#### Signal

```
signal_id: UUID
type: string
payload: json
created_at: timestamp
processed_at: timestamp|null
```

---

### 3.2 Lifecycle rules

* Notes: immutable.
* Beliefs:

  * proposed → active
  * active ↔ challenged
  * challenged → deprecated
  * deprecated → archived
* All transitions are logged and reversible.

---

## 4. Architecture — Concrete Build Targets

### 4.1 Required repository structure

```
second_brain/
├── core/
│   ├── models.py
│   ├── services/
│   │   ├── notes.py
│   │   ├── beliefs.py
│   │   ├── edges.py
│   │   ├── audit.py
│   │   └── signals.py
│   └── rules/
│       ├── confidence.py
│       ├── decay.py
│       └── contradictions.py
├── agents/
│   ├── ingestion.py
│   ├── synthesis.py
│   ├── challenger.py
│   └── curator.py
├── storage/
│   ├── sqlite.py
│   ├── migrations/
│   └── vector.py
├── runtime/
│   ├── dispatcher.py
│   └── scheduler.py
├── cli/
│   └── main.py
└── tests/
```

### 4.2 Storage implementation

* SQLite is the **single source of truth**.
* Graph is implemented via `edges` table.
* Vector index is **derived state** (rebuildable).
* No in-memory-only state allowed.

---

## 5. Agents — Explicit Responsibilities

### 5.1 IngestionAgent

**Input:** CLI add, file import
**Output:** Note, Source, embedding, signal

Steps:

1. Create Source.
2. Create immutable Note.
3. Extract tags/entities (regex + keyword list only).
4. Compute embedding.
5. Emit `signal:new_note`.

---

### 5.2 SynthesisAgent

**Input:** `signal:new_note`, scheduled run
**Output:** proposed Beliefs

Steps:

1. Group notes by shared tags/entities.
2. Generate belief candidates (string templates or LLM).
3. Create Belief with `status=proposed`.
4. Create `supports` edges.
5. Emit `signal:belief_proposed`.

---

### 5.3 ChallengerAgent

**Input:** `signal:belief_proposed`, `signal:new_note`
**Output:** state changes, contradiction edges

Rules:

* Exact negation detection.
* Same-subject opposing predicates.
* Confidence drop if contradiction exists.

Actions:

* Add `contradicts` edge.
* Set belief → `challenged`.
* Emit `signal:belief_challenged`.

---

### 5.4 CuratorAgent

**Input:** scheduled run
**Output:** archive, merge, distillation

Rules:

* Cold if not referenced in N days.
* Duplicate if cosine similarity ≥ threshold.

Actions:

* Archive with grace period.
* Merge notes/beliefs.
* Create summary notes.

---

## 6. Belief Management — Deterministic Rules

### 6.1 Confidence formula

```
confidence =
  clamp(
    (Σ support_weights − Σ counter_weights)
    * decay(time_since_last_update),
    0.0,
    1.0
  )
```

### 6.2 Status transitions

| From       | To         | Condition                                              |
| ---------- | ---------- | ------------------------------------------------------ |
| proposed   | active     | confidence ≥ activation_threshold AND no contradiction |
| active     | challenged | contradiction exists                                   |
| challenged | deprecated | counterevidence dominates                              |
| deprecated | archived   | curator policy                                         |

All transitions:

* transactional
* logged
* reversible

---

## 7. Interaction Pipelines (Executable)

### 7.1 Add pipeline

```
CLI add
 → IngestionAgent
 → Note + Source persisted
 → Embedding stored
 → signal:new_note
```

### 7.2 Ask pipeline

```
CLI ask
 → keyword search (FTS)
 → vector search
 → retrieve active beliefs
 → assemble evidence pack
 → synthesize answer (LLM optional)
 → validate citations
 → output answer + evidence IDs
```

### 7.3 Proactive pipeline

```
Scheduler tick
 → CuratorAgent
 → ChallengerAgent
 → SynthesisAgent
 → Generate report artifacts
```

---

## 8. Evolution Controls

### 8.1 Feedback

User actions emit signals:

* `belief_confirmed`
* `belief_refuted`
* `source_trust_updated`

Agents must respond deterministically.

### 8.2 Anti-rot policies

* Mandatory decay.
* Mandatory archive review.
* Mandatory duplicate detection.
* No silent deletion.

---

## 9. Security & Integrity

### 9.1 Integrity

* Foreign keys enforced.
* Note content hashed.
* Edge referential checks.

### 9.2 Audit & rollback

* Append-only audit log.
* Snapshot + restore commands.

### 9.3 LLM constraints

* Evidence-only context.
* Uncited claims rejected.
* LLM output never directly mutates beliefs.

---

## 10. Implementation Phases — AI-Executable Task Lists

### Phase 0 — Capture

1. SQLite schema + migrations.
2. Note + Source services.
3. CLI add/search/show.
4. FTS.
5. Persistence tests.

**Exit:** notes persist, searchable, audited.

---

### Phase 1 — Reasoning

1. Belief + Edge services.
2. Confidence + decay rules.
3. Challenger heuristics.
4. Vector embeddings.
5. Ask pipeline with citations.
6. Synthesis + Challenger agents.

**Exit:** beliefs tracked, contradictions handled, answers grounded.

---

### Phase 2 — Proactive

1. Scheduler + dispatcher.
2. CuratorAgent.
3. Archive/merge/distill.
4. Reports.
5. Snapshot/restore.
6. Long-run integrity tests.

**Exit:** self-maintaining system with full auditability.

---

## Final Sufficiency Statement

This document:

* Defines **all objects**, **all transitions**, **all agents**, and **all execution order**.
* Specifies **what code must exist**, **where**, and **why**.
* Leaves **no semantic gaps** requiring follow-up questions.
* Is directly consumable by a coding agent.

If you want the *next* iteration, the only remaining step is to turn this into **a file-by-file code-generation prompt** (one file per prompt, enforced order).
