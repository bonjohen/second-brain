# System Code Review
Generated: 2026-02-10
Project: second-brain (225 tests, 19 test files, ~2800 LOC)

---

## 1. Structural & Architectural

```
[🟠 HIGH] Structural > God Module — cli/main.py
  File: second_brain/cli/main.py (472 lines)
  Evidence: Single file contains 12+ commands spanning ingestion, search, display,
            belief management, trust management, reporting, backup/restore, and
            scheduler execution.
  Impact: High cognitive load; difficult to test commands in isolation; violates
          single responsibility principle. Adding new commands increases coupling.
  Suggested Fix: Split into subcommand groups (e.g. cli/notes.py, cli/beliefs.py,
                 cli/admin.py) using Click's group/subgroup pattern.
```

```
[🟡 MEDIUM] Structural > Leaky Abstraction — DB path exposed to CLI
  File: second_brain/cli/main.py:44-50
  Evidence: Every CLI command receives `db_path` and manually constructs Database()
            objects. The fact that storage is SQLite at a file path is visible to
            the CLI layer.
  Impact: Replacing the storage layer (e.g. PostgreSQL) requires changing all CLI
          commands. Tight coupling between CLI and storage implementation.
  Suggested Fix: Create a service factory (e.g. `ServiceContainer`) that the CLI
                 instantiates once; commands receive pre-built services.
```

```
[🟡 MEDIUM] Structural > Dispatcher does not isolate handlers
  File: second_brain/runtime/dispatcher.py:49-53
  Evidence: Multiple handlers for a signal type run sequentially. If handler A
            succeeds and handler B throws, the signal is NOT marked processed.
            Next poll re-runs handler A (duplicate side effects).
  Impact: One broken handler blocks all handlers for that signal type. Successful
          handlers re-execute on retry, causing duplicate edges/signals.
  Suggested Fix: Track per-handler completion; only retry failed handlers. Or
                 document the limitation and add idempotency guards in handlers.
```

```
[🔵 LOW] Structural > Premature Abstraction — Unused continuous scheduler
  File: second_brain/runtime/scheduler.py:56-69
  Evidence: run_continuous() with tick_interval and max_ticks is implemented but
            only run_once() is used (by CLI `sb run`). Continuous mode has race
            condition issues (see Concurrency section).
  Impact: Dead code that introduces concurrency bugs if ever enabled.
  Suggested Fix: Remove run_continuous() until needed; document run_once() as the
                 only supported entry point.
```

---

## 2. Configuration & Environment

```
[🟡 MEDIUM] Configuration > Hardcoded limits with no documentation
  Files: Multiple locations
    - agents/curator.py:70 (limit=1000 for deprecated beliefs)
    - agents/curator.py:95 (limit=1000 for active beliefs)
    - agents/curator.py:102 (max_beliefs=200 for dedup)
    - agents/synthesis.py:77 (limit=100 for notes per tag)
    - core/rules/lifecycle.py:38 (batch_size=500)
    - core/rules/contradictions.py:35 (DEFAULT_MAX_CANDIDATES=500)
    - cli/main.py:345 (limit=100000 for report)
    - cli/main.py:350 (limit=100000 for report beliefs)
    - cli/main.py:375 (< 0.3 low confidence threshold)
  Evidence: Multiple hard-coded limits scattered across modules with no central
            configuration, no documentation, and no tests at boundaries.
  Impact: Cannot tune without code changes; inconsistent behavior if one copy
          is changed; silent data loss when limits are exceeded.
  Suggested Fix: Extract to a config dict or dataclass; document limits in
                 USAGE.md; add boundary tests.
```

```
[🟡 MEDIUM] Configuration > Confidence formula weights not configurable
  Files: core/rules/confidence.py:14-16, core/models.py:142,
         core/services/beliefs.py:39
  Evidence: Three separate `0.5` defaults for base confidence, plus hardcoded
            support_weight=0.1 and contradiction_weight=0.1 in the formula.
  Impact: Changing the formula requires editing source code in multiple files.
          No single source of truth for the default confidence value.
  Suggested Fix: Single config constant for base confidence; weights already
                 parameterized via compute_confidence() args.
```

```
[🔵 LOW] Configuration > Missing .env.example / config documentation
  File: (repository root — file missing)
  Evidence: SB_DB_PATH environment variable is supported but not documented in
            a .env.example or config schema. Users must read source to discover it.
  Impact: Discovery friction for new users.
  Suggested Fix: Add .env.example with SB_DB_PATH.
```

---

## 3. Error Handling & Observability

```
[🔴 CRITICAL] [FIXED] Error Handling > DB resource leak on CLI error paths
  File: second_brain/cli/main.py — multiple commands
    - show(): lines 139, 144 exit before db.close() at 157
    - confirm(): lines 267, 272 exit before db.close() at 278
    - refute(): lines 293, 298 exit before db.close() at 304
    - trust(): lines 318, 324 exit before db.close() at 331
    - snapshot(): line 407 exits before db.close() at 414
    - restore(): line 427 exits without closing db
  Evidence: `raise SystemExit(1)` on error paths bypasses db.close(). Database
            connection is never explicitly released.
  Impact: SQLite WAL files may remain locked; "database is locked" errors on
          subsequent runs; resource leak accumulation.
  Suggested Fix: Use try/finally or context manager pattern for Database in every
                 CLI command.
```

```
[🟠 HIGH] [FIXED] Error Handling > Bare except with silent pass in ask command
  File: second_brain/cli/main.py:178-185
  Evidence: `except Exception: pass` swallows ALL exceptions from vector search,
            including database failures, UUID parse errors, and corrupt embeddings.
            Comment says "graceful fallback if embeddings not available".
  Impact: Real errors become invisible; impossible to debug vector search failures.
  Suggested Fix: Catch specific ImportError/AttributeError for missing embeddings;
                 log unexpected exceptions.
```

```
[🟠 HIGH] Error Handling > Swallowed exception in search_notes()
  File: second_brain/core/services/notes.py:151-152
  Evidence: `except sqlite3.OperationalError: return []` — no logging or indication
            of failure. Callers cannot distinguish "no results" from "search crashed".
  Impact: FTS5 setup errors, missing tables, or malformed queries are silently
          masked as empty results.
  Suggested Fix: Log a warning with the exception; consider raising for non-FTS5
                 OperationalErrors.
```

```
[🟠 HIGH] [FIXED] Error Handling > Missing error handling in agent pipelines
  Files:
    - agents/ingestion.py:74-76 — vector store operations unprotected
    - agents/challenger.py:55-59 — detect_contradictions() unprotected
    - agents/challenger.py:82 — compute_confidence() unprotected
    - agents/synthesis.py:48-51 — UUID parsing from signal payload unprotected
  Evidence: Agent methods call downstream services without try/except. A single
            failure crashes the entire agent pipeline for that tick.
  Impact: One bad note, belief, or signal halts all processing for that agent type.
  Suggested Fix: Add per-item try/except with logging in agent loops; continue
                 processing remaining items.
```

```
[🟠 HIGH] [FIXED] Error Handling > Partial state mutation in ChallengerAgent
  File: second_brain/agents/challenger.py:76-83
  Evidence: Belief status is updated to CHALLENGED (line 78) before confidence is
            recomputed (line 82). If confidence computation fails, the belief has
            been modified without the corresponding confidence update.
  Impact: Beliefs can end up in CHALLENGED status with stale confidence scores.
  Suggested Fix: Compute confidence first, then update both status and confidence
                 atomically.
```

```
[🟡 MEDIUM] Error Handling > JSON decode errors not handled in row conversion
  Files:
    - core/services/notes.py:206-207 — json.loads(row["tags"]), json.loads(row["entities"])
    - core/services/beliefs.py:177 — json.loads(row["scope"])
    - core/services/signals.py:71 — json.loads(row["payload"])
    - core/services/audit.py:78-79 — json.loads(before_json), json.loads(after_json)
  Evidence: All JSON deserialization in _row_to_* methods lack try/except. Corrupted
            JSON in one row crashes the entire query result.
  Impact: A single corrupted database row can make an entire table unreadable.
  Suggested Fix: Add try/except JSONDecodeError with fallback (empty dict/list) and
                 warning log.
```

```
[🟡 MEDIUM] Error Handling > Dispatcher retry loop has no backoff
  File: second_brain/runtime/dispatcher.py:49-58
  Evidence: Failed signals are not marked processed and will be retried immediately
            on next dispatch_once() call. No delay, backoff, or max retry count.
  Impact: A permanently failing handler causes busy-spin retries consuming CPU.
  Suggested Fix: Add retry count tracking per signal; skip signals exceeding max
                 retries with a log warning.
```

```
[🟡 MEDIUM] Error Handling > Scheduler catches all exceptions uniformly
  File: second_brain/runtime/scheduler.py:44-48
  Evidence: `except Exception` handles all errors the same way — increment counter
            and log. No distinction between transient failures and programming bugs.
  Impact: Bugs are masked the same way as transient errors.
  Suggested Fix: Differentiate known recoverable errors from unexpected exceptions;
                 consider re-raising on repeated failures.
```

```
[🟡 MEDIUM] Error Handling > Silent skip of unhandled signal types
  File: second_brain/runtime/dispatcher.py:42-47
  Evidence: If no handler is registered for a signal type, the signal is marked
            processed and silently discarded.
  Impact: Configuration errors (forgot to register a handler) or new signal types
          disappear without alerting developers.
  Suggested Fix: Log a warning when discarding signals with no registered handler.
```

```
[🔵 LOW] Error Handling > Scheduler failure counter never consumed
  File: second_brain/runtime/scheduler.py:27, 45
  Evidence: failure_counts dict is incremented on errors but never read, reset,
            or used to trigger alerts.
  Impact: Metrics collected but never acted on; dead code.
  Suggested Fix: Expose failure_counts in tick() return value or add threshold
                 alerting.
```

---

## 4. Data & State

```
[🟡 MEDIUM] Data & State > Unbounded query in get_unprocessed()
  File: second_brain/core/services/signals.py:36-56
  Evidence: Both query paths lack LIMIT. If unprocessed signals accumulate (e.g.
            100K+ rows after extended downtime), all are fetched into memory.
  Impact: Memory exhaustion; full table scan; potential timeout.
  Suggested Fix: Add limit parameter with sensible default (e.g. 1000).
```

```
[🟡 MEDIUM] Data & State > N+1 query pattern in lifecycle transitions
  File: second_brain/core/rules/lifecycle.py:36-56
  Evidence: For each belief in a batch, compute_confidence() calls
            edge_service.get_edges() individually. Pre-loaded contradiction
            candidates mitigate the worst case, but edge queries remain per-belief.
  Impact: 500 proposed beliefs = 500 separate edge queries.
  Suggested Fix: Batch-load edges for all beliefs in the batch; pass pre-loaded
                 edge map to compute_confidence().
```

```
[🟡 MEDIUM] Data & State > TEXT timestamps instead of native SQLite types
  File: second_brain/storage/migrations/001_initial_schema.sql:7,14,31,45
  Evidence: All timestamps stored as TEXT (ISO 8601 strings). SQLite cannot use
            time-based indexes efficiently; date arithmetic requires string parsing.
  Impact: Range queries ("notes created in last 7 days") are slow and fragile.
  Suggested Fix: Accept as design tradeoff (documented); or migrate to INTEGER
                 (unix timestamps) in a future schema version.
```

```
[🟡 MEDIUM] Data & State > Datetime parsing fragile and duplicated
  Files: core/rules/confidence.py:40-44, agents/curator.py:70-73
  Evidence: `isinstance(updated_at, str) → fromisoformat() → patch UTC` pattern
            was duplicated. Now extracted to parse_utc_datetime() but _row_to_*
            methods still pass raw strings to Pydantic models without using it.
  Impact: Timezone-naive datetimes may slip through row conversion paths.
  Suggested Fix: Apply parse_utc_datetime() in _row_to_belief() and _row_to_note()
                 for created_at/updated_at fields.
```

```
[🟡 MEDIUM] Data & State > Edge table has no referential integrity
  File: second_brain/core/services/edges.py:16-46
  Evidence: Edges table has no FK constraints (by design, for polymorphism).
            create_edge() performs no validation that from_id or to_id exist.
  Impact: Dangling edges pointing to deleted entities accumulate silently.
  Suggested Fix: Add optional validate_referential_integrity() method; or add
                 periodic cleanup in CuratorAgent.
```

```
[🔵 LOW] Data & State > Inconsistent null handling in row conversion
  File: second_brain/core/services/signals.py:67-74
  Evidence: processed_at is explicitly coerced to None, but created_at is passed
            as-is from the database (string).
  Impact: Type inconsistency; potential model validation surprises.
  Suggested Fix: Normalize both timestamp fields consistently.
```

---

## 5. Testing & Quality

```
[🔴 CRITICAL] [FIXED] Testing > Test documents bug as expected behavior
  File: tests/test_dispatcher.py:80-102
  Evidence: test_dispatch_partial_handler_failure asserts that handler A runs twice
            (duplicate side effects). The test passes when buggy behavior occurs.
  Impact: Any fix to prevent duplicate side effects will break this test. The test
          actively prevents fixing the underlying idempotency bug.
  Suggested Fix: Rename to test_dispatch_partial_handler_failure_known_limitation;
                 add a TODO and link to a tracking issue.
```

```
[🟠 HIGH] Testing > Implementation-coupled tests (mocking internals)
  Files:
    - tests/test_synthesis.py:111-129 — replaces list_notes at runtime
    - tests/test_lifecycle.py:74-98 — identical pagination tracking
    - tests/test_curator.py:245-264 — identical pattern
    - tests/test_curator.py:180-194 — patches update_belief_status
    - tests/test_vector.py:135-138 — asserts private _model attribute
  Evidence: Tests replace internal methods or check private attributes. They test
            implementation details rather than behavior.
  Impact: Tests break on refactors even when behavior is preserved.
  Suggested Fix: Test through public interfaces; use integration-style assertions
                 on observable outputs.
```

```
[🟠 HIGH] Testing > Missing negative/edge-case tests on critical paths
  Files:
    - tests/test_notes.py — no tests for duplicate content hash, concurrent creation
    - tests/test_beliefs.py — only 1 of 5 invalid status transitions tested
    - tests/test_rules.py — no boundary tests for confidence (division by zero,
      extreme edge counts, custom weights summing to 0)
    - tests/test_edges.py — direction="both" not tested for double-counting
  Evidence: ~70% of tests are happy-path only. Error conditions, boundary values,
            and malformed input are sparsely covered.
  Impact: Silent failures and data corruption risks undetected.
  Suggested Fix: Add negative test cases for each critical path identified above.
```

```
[🟠 HIGH] Testing > Test-prod parity gap — mocked vector store
  File: tests/test_curator.py:142-158
  Evidence: Tests use MagicMock for VectorStore with hardcoded return values
            (np.ones(384), cosine_similarity=0.99). Real model may return different
            dimensions, precision, or throw on certain inputs.
  Impact: Tests pass but production fails on real embeddings.
  Suggested Fix: Add at least one integration test with real sentence-transformers
                 (skip if not installed).
```

```
[🟠 HIGH] Testing > Missing signal pipeline integration tests
  File: (no dedicated integration test file)
  Evidence: Individual agents, signals, and dispatcher are tested in isolation.
            No test covers the full signal → dispatcher → agent → handler flow.
  Impact: Signal routing bugs, ordering issues, and cross-agent interactions
          undetected until E2E.
  Suggested Fix: Add tests/test_integration.py covering note ingestion → synthesis
                 → challenger → curator pipeline.
```

```
[🟡 MEDIUM] Testing > Missing performance/load tests
  File: (no performance test files)
  Evidence: No tests for FTS5 with >10000 notes, belief list with >1000 beliefs,
            edge traversal with >100 edges, or embedding store with >10000 vectors.
  Impact: Performance cliffs and O(n^2) algorithms not caught before production.
  Suggested Fix: Add benchmark tests in tests/test_benchmarks.py (can be skipped
                 by default, run explicitly).
```

```
[🟡 MEDIUM] Testing > CLI test creates concurrent DB connections
  File: tests/test_cli.py:87-116
  Evidence: test_ask_with_beliefs creates a second Database connection to the same
            file while the CLI runner holds another. Both open simultaneously.
  Impact: Violates single-connection assumption; tests may pass by timing accident.
  Suggested Fix: Use the same Database instance or close the CLI connection first.
```

```
[🟡 MEDIUM] Testing > Race condition in scheduler timing test
  File: tests/test_scheduler.py:48-72
  Evidence: test_run_continuous_max_ticks uses 10ms tick interval. On slow CI,
            timing may vary.
  Impact: Non-deterministic test failures under load.
  Suggested Fix: Use max_ticks-based termination without relying on timing; or
                 increase interval margin.
```

---

## 6. Dependency & Build

```
[🟡 MEDIUM] Dependency > Broad version ranges for major dependencies
  File: pyproject.toml:9-10
  Evidence: `sentence-transformers>=2.7,<4` spans a major version boundary.
            `numpy>=1.26,<3` similarly broad.
  Impact: Breaking API changes in major versions may slip in; non-reproducible
          builds across environments.
  Suggested Fix: Pin to current major version (e.g. >=2.7,<3 for
                 sentence-transformers).
```

```
[🔵 LOW] Dependency > No lockfile committed
  File: (repository root)
  Evidence: ⚠️ POSSIBLE — uv.lock may exist but was not verified. If using uv sync,
            uv.lock should be committed for reproducibility.
  Impact: Different dependency versions across developer machines.
  Suggested Fix: Verify uv.lock is committed; add to .gitignore check.
```

---

## 7. Security

```
[🟡 MEDIUM] Security > Dynamic SQL construction via f-string interpolation
  Files:
    - core/services/notes.py:189
    - core/services/edges.py:85
  Evidence: WHERE clauses are assembled with f-string interpolation:
            `f"SELECT * FROM notes {where} ORDER BY ..."` and
            `f"SELECT * FROM edges WHERE {where}"`.
            While current values come from enum.value (safe), the pattern is
            fragile if ever extended to accept untrusted input.
  Impact: Not currently exploitable (enum values are controlled), but violates
          defense-in-depth. Future modifications could introduce SQL injection.
  Suggested Fix: Document that WHERE construction must only use parameterized
                 values; consider using a query builder.
```

```
[🟡 MEDIUM] Security > Unvalidated JSON deserialization from database
  Files: (same as Error Handling finding — cross-referenced)
    - core/services/notes.py:206-207
    - core/services/beliefs.py:177
    - core/services/signals.py:71
    - core/services/audit.py:78-79
  Evidence: json.loads() on database fields without error handling. Corrupt data
            crashes the service.
  Impact: A single corrupted row makes an entire table unreadable through the
          service API.
  Suggested Fix: Wrap in try/except JSONDecodeError; return safe default with
                 warning log.
```

```
[🔵 LOW] Security > No input validation on CLI limit parameter
  File: second_brain/cli/main.py:112
  Evidence: `@click.option("--limit", "-n", default=10)` accepts any integer
            including negative values or extremely large numbers.
  Impact: Memory exhaustion on very large limits; unexpected behavior on negative.
  Suggested Fix: Add `type=click.IntRange(min=1, max=10000)`.
```

---

## 8. Code Hygiene

```
[🟡 MEDIUM] Code Hygiene > Magic numbers in CLI commands
  File: second_brain/cli/main.py — throughout
  Evidence: Hardcoded values with no named constants:
    - [:120] snippet truncation (line 122)
    - [:200] snippet truncation (line 225)
    - [:100] first line truncation (line 241)
    - +0.1/-0.1 confidence adjustments (lines 274, 300)
    - <0.3 low confidence threshold (line 375)
    - limit=100000 report queries (lines 345, 350)
  Impact: Values difficult to find and change; no semantic meaning attached.
  Suggested Fix: Extract to named constants at module top.
```

```
[🟡 MEDIUM] Code Hygiene > Stop words set recreated on every loop iteration
  File: second_brain/core/rules/contradictions.py:105-126
  Evidence: The stop_words set is defined inside the `for other in candidates`
            loop body, recreating it on every iteration.
  Impact: Unnecessary memory allocation per candidate (500+ iterations).
  Suggested Fix: Move stop_words to module-level constant.
```

```
[🟡 MEDIUM] Code Hygiene > Duplicated batch_size constants
  Files: core/rules/contradictions.py:50, core/rules/lifecycle.py:38
  Evidence: Both use `batch_size = 500` independently. Not shared.
  Impact: Divergence risk if one is changed without the other.
  Suggested Fix: Extract to shared constant.
```

```
[🔵 LOW] Code Hygiene > Inconsistent SystemExit patterns
  File: second_brain/cli/main.py — multiple lines
  Evidence: Some exits use `raise SystemExit(1) from None` (suppress chaining),
            others use `raise SystemExit(1)` (no suppression). All use exit code 1
            regardless of error type.
  Impact: Inconsistent style; cannot programmatically distinguish error types.
  Suggested Fix: Standardize on `from None` for all user-facing errors; consider
                 different exit codes for different error classes.
```

```
[🔵 LOW] Code Hygiene > Distillation tag magic strings
  File: second_brain/agents/curator.py:215, 230, 235
  Evidence: "distill-" prefix and "summary" tag hardcoded in three places.
  Impact: If naming convention changes, multiple locations must be updated.
  Suggested Fix: Extract to class-level constants.
```

```
[🔵 LOW] Code Hygiene > Redundant null check in Signal creation
  File: second_brain/core/services/signals.py:18-20
  Evidence: `payload=payload or {}` is redundant — Signal model already defaults
            payload to empty dict via Field(default_factory=dict).
  Impact: No functional issue; unnecessary defensive code.
  Suggested Fix: Remove `or {}`.
```

---

## 9. Concurrency & Performance

```
[🟠 HIGH] Concurrency > O(n^2) dedup with no timeout
  File: second_brain/agents/curator.py:120-124
  Evidence: Nested loop compares each belief embedding pair. Capped at max_beliefs
            =200 (20k comparisons), but no timeout or iteration limit exists.
  Impact: With max_beliefs raised, dedup can consume significant CPU time with no
          early exit.
  Suggested Fix: Add a time budget (e.g. 30s) with early exit; or use approximate
                 nearest neighbors for large sets.
```

```
[🟡 MEDIUM] Concurrency > Race condition on scheduler _running flag
  File: second_brain/runtime/scheduler.py:26, 62, 64, 73
  Evidence: _running is a plain bool set from run_continuous() and checked in a
            while loop. stop() sets it from potentially another thread. No
            synchronization primitive.
  Impact: In multithreaded scenarios, stop() may not immediately halt the loop.
  Suggested Fix: Use threading.Event instead of bool; or document single-threaded
                 constraint.
```

```
[🟡 MEDIUM] Concurrency > No timeout on agent steps
  File: second_brain/runtime/scheduler.py:41
  Evidence: Agent steps called with no timeout. A hung agent blocks the entire
            scheduler indefinitely.
  Impact: Single hung agent prevents all other agents from running.
  Suggested Fix: Add configurable per-step timeout; use threading.Timer or
                 signal.alarm.
```

```
[🟡 MEDIUM] Concurrency > Unbounded pagination in distill_notes()
  File: second_brain/agents/curator.py:192-201
  Evidence: distill_notes() paginates all notes into memory (batch_size=1000 but
            no total limit). For 100K+ notes, all are loaded.
  Impact: Memory pressure scales linearly with note count.
  Suggested Fix: Process tags incrementally; don't load all notes at once.
```

```
[🔵 LOW] Concurrency > Thread safety not documented on services
  Files: All service files (core/services/*.py)
  Evidence: Services accept Database instances and call db.execute(). Database
            enforces single-thread ownership, but services have no guards or
            documentation about thread safety.
  Impact: Users may share service instances across threads, causing crashes.
  Suggested Fix: Add docstring noting services are NOT thread-safe.
```

---

## 10. API & Contract Design

```
[🟡 MEDIUM] API Design > Inconsistent error semantics across services
  Files:
    - core/services/notes.py:60-82 — update_source_trust() raises ValueError
    - core/services/notes.py:50-57 — get_source() returns None
    - core/services/beliefs.py — update methods raise; get methods return None
    - core/services/edges.py:90-95 — delete_edge() silently succeeds on non-existent
  Evidence: Some methods raise on missing entities, some return None, some silently
            succeed. No consistent contract.
  Impact: Callers must handle both exception and None patterns; easy to miss errors.
  Suggested Fix: Establish convention: get_* returns Optional; update_*/delete_*
                 raise on missing; document in base class or README.
```

```
[🟡 MEDIUM] API Design > No validation of direction parameter
  File: second_brain/core/services/edges.py:48-88
  Evidence: direction accepts any string but only "outgoing", "incoming", and None
            are documented. Any typo (e.g. "outgoings") silently falls through to
            the else clause returning both directions.
  Impact: Silent behavior change on typo.
  Suggested Fix: Use an enum or Literal type; raise ValueError on invalid input.
```

```
[🔵 LOW] API Design > Inconsistent function signatures across list methods
  Files: core/services/beliefs.py:148-164 vs core/services/notes.py:155-192
  Evidence: Both use limit=50, offset=0 defaults, but filter parameters differ in
            naming and position across similar methods.
  Impact: Cognitive load on API users.
  Suggested Fix: Standardize: filters first, then limit, offset.
```

---

## 11. Process & Lifecycle

```
[🟡 MEDIUM] Process > Migration idempotency not enforced
  File: second_brain/storage/sqlite.py:122-131
  Evidence: Comment documents requirement for IF NOT EXISTS guards in migrations,
            but this is not enforced programmatically. A migration without guards
            will fail on re-run after partial application.
  Impact: Half-applied migrations cause crash loops with no recovery path.
  Suggested Fix: Add a pre-check that validates migration SQL contains IF NOT EXISTS
                 for DDL statements; or wrap migrations in savepoints.
```

```
[🔵 LOW] Process > No CODEOWNERS file
  File: (repository root — file missing)
  Evidence: No CODEOWNERS file; no clear ownership model for different modules.
  Impact: No automatic review assignment; unclear escalation path.
  Suggested Fix: Add CODEOWNERS if team expands beyond solo developer.
```

---

## Summary Table

| Category | CRITICAL | HIGH | MEDIUM | LOW | Total |
|----------|----------|------|--------|-----|-------|
| 1. Structural & Architectural | 0 | 1 | 2 | 1 | 4 |
| 2. Configuration & Environment | 0 | 0 | 2 | 1 | 3 |
| 3. Error Handling & Observability | 1 | 4 | 4 | 1 | 10 |
| 4. Data & State | 0 | 0 | 5 | 1 | 6 |
| 5. Testing & Quality | 1 | 4 | 3 | 0 | 8 |
| 6. Dependency & Build | 0 | 0 | 1 | 1 | 2 |
| 7. Security | 0 | 0 | 2 | 1 | 3 |
| 8. Code Hygiene | 0 | 0 | 3 | 3 | 6 |
| 9. Concurrency & Performance | 0 | 1 | 3 | 1 | 5 |
| 10. API & Contract Design | 0 | 0 | 2 | 1 | 3 |
| 11. Process & Lifecycle | 0 | 0 | 1 | 1 | 2 |
| **Totals** | **2** | **10** | **28** | **12** | **52** |

---

## Top 5 Priority Fixes

Ordered by impact-to-effort ratio (highest first):

1. **DB resource leak on CLI error paths** (CRITICAL, effort: low)
   Add try/finally around Database usage in all CLI commands. ~30 minutes of work
   prevents database locking issues affecting every user.

2. **Bare except with silent pass in ask command** (HIGH, effort: low)
   Replace `except Exception: pass` with specific exception types and logging.
   5-minute fix that restores observability for vector search failures.

3. **Test documents bug as expected behavior** (CRITICAL, effort: low)
   Rename/annotate the test; file a tracking issue for the dispatcher duplicate
   side-effect bug. Prevents the test from blocking future correctness fixes.

4. **Missing error handling in agent pipelines** (HIGH, effort: medium)
   Add per-item try/except in ingestion, challenger, and synthesis agent loops.
   ~1 hour of work prevents one bad record from halting all processing.

5. **Partial state mutation in ChallengerAgent** (HIGH, effort: low)
   Reorder operations: compute confidence before updating status. 10-minute fix
   prevents data inconsistency in the belief lifecycle.

---

## Categories That Cannot Be Fully Evaluated

The following checklist items require runtime or infrastructure analysis beyond static review:

- **Symptom-based alerting** (3. Error Handling): No production alerting system exists; cannot evaluate alert quality.
- **Missing health checks** (3. Error Handling): Application is CLI-only; liveness/readiness probes not applicable.
- **Stale caches** (4. Data & State): No caching layer exists beyond SQLite's page cache.
- **Non-reproducible deploys** (11. Process): No deployment pipeline exists; application is installed locally.
- **Frequently broken trunk** (11. Process): Would require CI history analysis.
- **Dependency vulnerabilities** (7. Security): Would require `pip audit` or `safety check` scan.
