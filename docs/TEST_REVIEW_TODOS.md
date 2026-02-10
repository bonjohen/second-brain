# Test Review TODOs
Generated: 2026-02-10
Project: second-brain

## Summary

The project has a solid foundation: 191 tests cover happy paths well across all services, agents, and CLI commands, with good test isolation via per-test temporary databases. The most concerning gaps are (1) a CLI command that bypasses the service layer to mutate the database directly (unaudited, untested error path), (2) the vector search loading all embeddings into memory on every query, and (3) zero concurrency/thread-safety testing despite the scheduler running agents that share a single DB connection.

## Critical (fix before next release)

- [X] **State Management** `cli/main.py:320-324` -- The `trust` command accesses `db._conn` directly, bypassing `Database.execute()`, audit logging, and service-layer validation. Any failure here leaves the DB in an inconsistent state with no audit trail. **Risk**: Untracked mutations, broken encapsulation, no rollback on error. **Action**: Create a `NoteService.update_source_trust()` method that uses `self._db.execute()` and logs to audit; replace the raw SQL in the CLI.

- [X] **Error Handling & Failure Modes** `agents/curator.py:142-150` -- Deduplication forces a multi-step state transition (PROPOSED->ACTIVE->CHALLENGED->DEPRECATED) that will throw `ValueError` if the belief is in an unexpected state (e.g. already CHALLENGED). The `try/except` around this block is missing entirely. **Risk**: One malformed belief crashes the entire curator run, preventing archive and distill from executing. **Action**: Add a test that calls `deduplicate_beliefs()` with beliefs in CHALLENGED status; wrap the transition chain in a try/except or add a `force_deprecate` helper.

- [X] **Resource Management** `storage/vector.py:56` -- `search_similar()` calls `fetchall("SELECT note_id, embedding FROM embeddings")`, loading every embedding BLOB into memory on every query. With 10k notes at 384-dim float32, that's ~15MB per query. **Risk**: OOM or severe latency at scale. **Action**: Add a test that inserts 1000 embeddings and measures memory/time; consider adding a `LIMIT` with pagination or SQLite's `sqlite-vec` extension.

- [X] **State Management** `storage/sqlite.py:31-39` -- `Database.connection()` yields the single `self._conn` instance. If the scheduler runs agents concurrently (or if two CLI commands share a DB path), interleaved commits/rollbacks will corrupt each other. **Risk**: Data corruption on concurrent access. **Action**: Add a test that runs two concurrent `connection()` contexts and verifies isolation; document that `Database` is single-threaded only, or switch to a connection-per-context pattern.

## High (address this sprint)

- [X] **Error Handling & Failure Modes** `runtime/dispatcher.py:49-58` -- When one handler in a multi-handler chain raises an exception, the signal is left unprocessed and *all* handlers will re-execute on the next poll, including the ones that already succeeded. **Risk**: Duplicate side effects (duplicate edges, duplicate signals emitted) for the handlers that ran before the failure. **Action**: Add a test with two handlers where the second throws; verify the first handler's side effects don't double on retry.

- [X] **Input Validation & Boundaries** `core/services/notes.py:113-125` -- FTS5 MATCH accepts special syntax operators (`AND`, `OR`, `NOT`, `NEAR`, `*`, `"`, column filters). User-supplied queries pass directly to `WHERE notes_fts MATCH ?`. **Risk**: Unexpected query behavior or SQLite errors on malformed FTS5 syntax (e.g. unbalanced quotes crash the query). **Action**: Add tests with adversarial queries (`"`, `*`, `AND OR`, `column:value`) and either sanitize input or wrap in a try/except returning empty results.

- [X] **Data Pipeline & ETL** `core/rules/confidence.py:40-44` -- `updated_at` is parsed from string with `fromisoformat()` and patched with UTC if timezone-naive. This same fragile pattern is copy-pasted in `agents/curator.py:70-73`. **Risk**: A non-ISO timestamp string in the DB causes `ValueError`, crashing confidence computation for all beliefs in the batch. **Action**: Extract a shared `parse_utc_datetime(value)` helper; add a test with malformed timestamp strings to verify graceful handling.

- [X] **Performance & Resource Efficiency** `agents/curator.py:108-170` -- `deduplicate_beliefs()` computes embeddings for all beliefs (O(n)), then compares all pairs (O(n^2)). With 1000 beliefs this is 500k cosine similarity computations. **Risk**: Agent tick takes minutes+, blocking scheduler. **Action**: Add a benchmark test with 100+ beliefs; consider clustering or approximate nearest neighbors instead of brute-force.

- [X] **State Management** `agents/curator.py:175` -- `distill_notes()` loads all notes (`limit=10000`) and groups by tag in memory. **Risk**: Notes beyond the 10k limit are silently excluded from distillation. **Action**: Add a test that creates 10001 notes and verifies the 10001st is handled (or document the limit). Same issue at `storage/vector.py:71` (`rebuild_index` with `limit=10000`).

- [X] **API Design & Contracts** `core/services/audit.py:51-66` -- `get_history()` returns all audit entries with no pagination. A belief that's been updated thousands of times returns unbounded rows. **Risk**: Memory exhaustion on long-lived entities. **Action**: Add `limit`/`offset` params; add a test that creates 100+ audit entries and verifies pagination.

- [X] **Error Handling & Failure Modes** `storage/sqlite.py:101-109` -- If a migration SQL script fails mid-execution via `executescript()`, the migration is not recorded in `_migrations`, causing it to re-execute on next startup. But `executescript()` commits implicitly, so partial DDL may already be applied. **Risk**: Repeated startup crashes from half-applied migrations with no recovery path. **Action**: Add a test with a deliberately broken migration (syntax error after valid DDL) and verify the system can recover.

## Medium (tech debt backlog)

- [ ] **Input Validation & Boundaries** `core/models.py:77-101` -- `Note.content` has no maximum length validation. The FTS5 index and embedding computation will process arbitrarily large content. **Risk**: A multi-MB note causes slow indexing, large DB bloat, and embedding model truncation (BERT models truncate at 512 tokens silently). **Action**: Add a `max_length` validator on `content` (e.g. 100KB); add a test verifying rejection of oversized content.

- [ ] **Data Pipeline & ETL** `agents/synthesis.py:77,87` -- `list_notes(tag=tag, limit=100)` uses a hard limit. Tags with 101+ notes will produce beliefs based on an incomplete sample. **Risk**: Beliefs miss relevant evidence, confidence is underestimated. **Action**: Add a test that creates 101 notes with the same tag and verifies synthesis considers all of them; implement pagination or raise the limit.

- [ ] **Observability & Operability** `cli/main.py:35-40` -- When `sentence-transformers` is not installed, `vector_store` is silently set to `None`. No warning is logged or displayed. **Risk**: Users expect vector search but get silently degraded FTS-only results. **Action**: Add `click.echo("Warning: ...")` or `logging.warning()` when the import fails; add a test that mocks the ImportError and verifies the warning.

- [ ] **State Management** `core/services/edges.py:16-46` -- `create_edge()` performs no validation that `from_id` or `to_id` actually exist in their respective tables. The edges table has no FK constraints (by design, for polymorphism). **Risk**: Dangling edges pointing to deleted or nonexistent entities accumulate silently. **Action**: Add a test that creates an edge to a nonexistent belief UUID, then verifies `get_edges()` still works; consider adding a `validate_referential_integrity()` method to EdgeService.

- [ ] **Error Handling & Failure Modes** `core/services/edges.py:90-95` -- `delete_edge()` silently succeeds even if the edge doesn't exist (SQL `DELETE WHERE` matches 0 rows). **Risk**: Callers cannot distinguish between successful deletion and no-op. **Action**: Add a test that deletes a nonexistent edge_id and verifies behavior; return a boolean or raise if not found.

- [ ] **Security & Access Control** `cli/main.py:430-433` -- `restore` command overwrites the live database with `shutil.copy2()` without any confirmation prompt or backup of the current state. **Risk**: Accidental data loss from fat-finger restore. **Action**: Add a test verifying a restore overwrites; consider auto-snapshot before restore.

- [ ] **Performance & Resource Efficiency** `core/rules/contradictions.py:48-80` -- `detect_contradictions()` loads all PROPOSED+ACTIVE beliefs (limit 1000) and checks each pair against the target. **Risk**: O(n) per belief, called per-belief in lifecycle and challenger, making total cost O(n^2). **Action**: Add a benchmark test with 500+ beliefs; consider indexing or caching contradiction results.

- [ ] **State Management** `core/rules/lifecycle.py:31,47` -- `auto_transition_beliefs()` loads beliefs with `limit=1000`. Systems with >1000 proposed or challenged beliefs silently skip the overflow. **Risk**: Beliefs stuck in proposed/challenged limbo forever. **Action**: Add a test creating 1001 proposed beliefs and verifying all are evaluated; implement pagination loop.

- [X] **Data Pipeline & ETL** `agents/curator.py:117` -- `self._vector_store._cosine_similarity()` accesses a private method across class boundaries. **Risk**: Internal API change in VectorStore breaks CuratorAgent with no compile-time warning. **Action**: Make `_cosine_similarity` public (rename to `cosine_similarity`) or add a public `compare(a, b)` method.

## Low (hardening)

- [ ] **Input Validation & Boundaries** `agents/ingestion.py:extract_tags` -- Tag regex `#(\w[\w/-]*)` has no length limit. A tag like `#aaaa...` (10000 chars) will be stored without truncation. **Risk**: DB bloat, display issues. **Action**: Add a max tag length (e.g. 100 chars) in the extraction regex or post-filter; add a test with a very long tag.

- [ ] **API Design & Contracts** `core/models.py:139-149` -- `Edge` model allows `from_id == to_id` (self-loops). **Risk**: Self-referential edges could confuse graph traversal logic in confidence computation or contradiction detection. **Action**: Add a Pydantic validator that rejects `from_id == to_id` when `from_type == to_type`; add a test.

- [ ] **Configuration & Environment** `core/rules/confidence.py:58` -- The confidence formula `0.5 + 0.1 * supports - 0.1 * contradicts` uses hardcoded weights. Changing the formula requires editing source code. **Risk**: No tunability without code changes. **Action**: Extract weights to a config dict or constructor params; add a test that overrides the weights.

- [ ] **Observability & Operability** `runtime/scheduler.py:38-43` -- Step failures are caught with a bare `except Exception` and logged, but no metrics, retry counts, or alerting mechanism exists. **Risk**: Persistently failing agents go unnoticed. **Action**: Add a failure counter per step; add a test that verifies failure count increments on repeated failures.

- [ ] **Input Validation & Boundaries** `core/models.py:104-113` -- `Signal.payload` is `dict[str, Any]` with no schema validation. A signal with a 100MB payload would be serialized to JSON and stored. **Risk**: Memory/disk exhaustion from oversized payloads. **Action**: Add a Pydantic validator limiting payload to reasonable size (e.g. 64KB serialized); add a test.

- [X] **Error Handling & Failure Modes** `agents/curator.py:57-81` -- `archive_cold_beliefs()` catches no exceptions. If `update_belief_status()` raises for one belief (e.g. invalid transition), the entire archival loop aborts. **Risk**: One bad belief prevents archival of all subsequent beliefs in the batch. **Action**: Add per-belief try/except with logging; add a test where one belief in ARCHIVED status is mixed in with DEPRECATED beliefs.

## Observations

- **Test coverage is broad but shallow**: Every service and agent has happy-path tests, but error/failure paths are sparse. Only 30 of 191 tests exercise error conditions.
- **No concurrency testing exists**: The scheduler and dispatcher are designed for background processing, but no tests verify thread safety or signal ordering under concurrent access.
- **Datetime parsing is fragile and duplicated**: The `isinstance(updated_at, str) -> fromisoformat()` pattern appears in `confidence.py:40-44`, `curator.py:70-73`, and could appear anywhere timestamps cross the DB-to-Python boundary. A single helper would eliminate this class of bugs.
- **Hard-coded limits are pervasive**: `limit=1000`, `limit=10000`, `limit=100000` appear across services, agents, and rules. None are documented, configurable, or tested at boundaries.
- **Deduplication is the least-tested feature**: `CuratorAgent.deduplicate_beliefs()` is exercised only through `test_run_empty_system` (which returns 0). No test verifies actual merge logic, edge transfer, or state transitions during dedup.
- **The polymorphic edge table trades integrity for flexibility**: No FK constraints on edge endpoints means dangling references can silently accumulate. The service layer does no referential validation on create.
