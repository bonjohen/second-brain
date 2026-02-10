"""CLI entry point for Second Brain."""

from __future__ import annotations

import logging
import shutil
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import click

from second_brain.core.constants import (
    CONFIDENCE_STEP,
    LOW_CONFIDENCE_THRESHOLD,
    REPORT_QUERY_LIMIT,
    SNIPPET_FIRST_LINE,
    SNIPPET_MEDIUM,
    SNIPPET_SHORT,
)
from second_brain.core.models import ContentType, SourceKind, TrustLabel

logger = logging.getLogger(__name__)


def _get_services(db_path: str | None = None):
    """Construct and return all services and agents."""
    from second_brain.agents.ingestion import IngestionAgent
    from second_brain.core.services.audit import AuditService
    from second_brain.core.services.beliefs import BeliefService
    from second_brain.core.services.edges import EdgeService
    from second_brain.core.services.notes import NoteService
    from second_brain.core.services.signals import SignalService
    from second_brain.storage.sqlite import Database

    db = Database(db_path) if db_path else Database()
    audit = AuditService(db)
    signals = SignalService(db)
    notes = NoteService(db, audit)
    edges = EdgeService(db)
    beliefs = BeliefService(db, audit, edges)

    # Try to create vector store (graceful fallback if sentence-transformers unavailable)
    vector_store = None
    try:
        from second_brain.storage.vector import VectorStore

        vector_store = VectorStore(db)
    except ImportError:
        logger.warning(
            "sentence-transformers not installed; vector search disabled (FTS-only mode)"
        )

    agent = IngestionAgent(notes, signals, vector_store=vector_store)
    return db, notes, signals, agent, edges, beliefs, vector_store, audit


@click.group()
@click.option("--db", default=None, envvar="SB_DB_PATH", help="Path to SQLite database file.")
@click.pass_context
def cli(ctx: click.Context, db: str | None) -> None:
    """Second Brain -- local cognitive substrate."""
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db


@cli.command()
@click.argument("content", required=False)
@click.option("--tags", "-t", multiple=True, help="Tags to attach (repeatable).")
@click.option(
    "--type",
    "content_type",
    type=click.Choice([ct.value for ct in ContentType], case_sensitive=False),
    default="text",
    help="Content type.",
)
@click.option(
    "--source",
    "source_kind",
    type=click.Choice([sk.value for sk in SourceKind], case_sensitive=False),
    default="user",
    help="Source kind.",
)
@click.pass_context
def add(
    ctx: click.Context,
    content: str | None,
    tags: tuple[str, ...],
    content_type: str,
    source_kind: str,
) -> None:
    """Add a note. Reads from stdin if no CONTENT argument is given."""
    if content is None:
        if sys.stdin.isatty():
            click.echo("Enter note content (Ctrl+D to finish):")
        content = sys.stdin.read()

    if not content.strip():
        click.echo("Error: empty content.", err=True)
        raise SystemExit(1)

    db, _notes, _signals, agent, *_ = _get_services(ctx.obj["db_path"])
    try:
        source, note = agent.ingest(
            content=content,
            content_type=ContentType(content_type),
            source_kind=SourceKind(source_kind),
            extra_tags=list(tags) if tags else None,
        )
        click.echo(f"Note created: {note.note_id}")
        if note.tags:
            click.echo(f"Tags: {', '.join(note.tags)}")
        if note.entities:
            click.echo(f"Entities: {', '.join(note.entities)}")
    finally:
        db.close()


@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=10, help="Max results.")
@click.pass_context
def search(ctx: click.Context, query: str, limit: int) -> None:
    """Search notes by keyword (FTS5)."""
    db, notes_svc, *_ = _get_services(ctx.obj["db_path"])
    try:
        results = notes_svc.search_notes(query)[:limit]
        if not results:
            click.echo("No results found.")
        else:
            for note in results:
                snippet = note.content[:SNIPPET_SHORT].replace("\n", " ")
                click.echo(f"[{note.note_id}] {snippet}")
                if note.tags:
                    click.echo(f"  tags: {', '.join(note.tags)}")
    finally:
        db.close()


@cli.command()
@click.argument("note_id")
@click.pass_context
def show(ctx: click.Context, note_id: str) -> None:
    """Show a note by ID."""
    db, notes_svc, *_ = _get_services(ctx.obj["db_path"])
    try:
        try:
            uid = uuid.UUID(note_id)
        except ValueError:
            click.echo(f"Error: invalid UUID: {note_id}", err=True)
            raise SystemExit(1) from None

        note = notes_svc.get_note(uid)
        if note is None:
            click.echo(f"Note not found: {note_id}", err=True)
            raise SystemExit(1)

        source = notes_svc.get_source(note.source_id)

        click.echo(f"ID:           {note.note_id}")
        click.echo(f"Created:      {note.created_at.isoformat()}")
        click.echo(f"Type:         {note.content_type.value}")
        click.echo(f"Hash:         {note.content_hash}")
        click.echo(f"Source:       {source.kind.value if source else 'unknown'} ({note.source_id})")
        click.echo(f"Tags:         {', '.join(note.tags) if note.tags else '(none)'}")
        click.echo(f"Entities:     {', '.join(note.entities) if note.entities else '(none)'}")
        click.echo("---")
        click.echo(note.content)
    finally:
        db.close()


@cli.command()
@click.argument("question")
@click.option("--top-k", "-k", default=5, help="Number of results to consider.")
@click.pass_context
def ask(ctx: click.Context, question: str, top_k: int) -> None:
    """Ask a question and get an answer with evidence and beliefs."""
    db, notes_svc, _signals, _agent, edges_svc, beliefs_svc, vector_store, _audit = (
        _get_services(ctx.obj["db_path"])
    )
    try:
        from second_brain.core.models import EntityType

        # 1. FTS keyword search
        fts_results = notes_svc.search_notes(question)[:top_k]

        # 2. Vector similarity search (if available)
        vector_results = []
        if vector_store is not None:
            try:
                similar = vector_store.search_similar(question, top_k=top_k)
                for note_id_str, score in similar:
                    note = notes_svc.get_note(uuid.UUID(note_id_str))
                    if note:
                        vector_results.append((note, score))
            except Exception:
                logger.warning("Vector search failed; falling back to FTS-only", exc_info=True)

        # 3. Merge/dedup results
        seen: set[str] = set()
        evidence = []
        for note in fts_results:
            nid = str(note.note_id)
            if nid not in seen:
                seen.add(nid)
                evidence.append(note)

        for note, _score in vector_results:
            nid = str(note.note_id)
            if nid not in seen:
                seen.add(nid)
                evidence.append(note)

        # 4. Retrieve related beliefs via edges from matching notes
        related_beliefs = []
        belief_ids_seen: set[str] = set()
        for note in evidence:
            edges = edges_svc.get_edges(EntityType.NOTE, note.note_id, direction="outgoing")
            for edge in edges:
                if edge.to_type == EntityType.BELIEF:
                    bid_str = str(edge.to_id)
                    if bid_str not in belief_ids_seen:
                        belief_ids_seen.add(bid_str)
                        belief = beliefs_svc.get_belief(edge.to_id)
                        if belief:
                            related_beliefs.append(belief)

        # 5. Display results
        if not evidence and not related_beliefs:
            click.echo("No evidence found.")
            return

        if evidence:
            click.echo("=== Evidence Notes ===")
            for i, note in enumerate(evidence, 1):
                snippet = note.content[:SNIPPET_MEDIUM].replace("\n", " ")
                click.echo(f"  [{i}] ({note.note_id}) {snippet}")
                if note.tags:
                    click.echo(f"      tags: {', '.join(note.tags)}")

        if related_beliefs:
            click.echo("\n=== Related Beliefs ===")
            for belief in related_beliefs:
                click.echo(
                    f"  - [{belief.status.value}] (confidence: {belief.confidence:.2f}) "
                    f"{belief.claim_text}"
                )

        click.echo("\n=== Answer ===")
        click.echo(f"Based on {len(evidence)} evidence note(s):")
        for i, note in enumerate(evidence, 1):
            first_line = note.content.split("\n")[0][:SNIPPET_FIRST_LINE]
            click.echo(f"  [{i}] {first_line}")

        if related_beliefs:
            click.echo(f"\nRelated beliefs ({len(related_beliefs)}):")
            for belief in related_beliefs:
                click.echo(f"  - {belief.claim_text} (confidence: {belief.confidence:.2f})")
    finally:
        db.close()


# ── Phase 2 Commands ──────────────────────────────────────────────────


@cli.command()
@click.argument("belief_id")
@click.pass_context
def confirm(ctx: click.Context, belief_id: str) -> None:
    """Confirm a belief -- boost its confidence."""
    db, _notes, signals, _agent, edges_svc, beliefs_svc, _vs, _audit = _get_services(
        ctx.obj["db_path"]
    )
    try:
        try:
            bid = uuid.UUID(belief_id)
        except ValueError:
            click.echo(f"Error: invalid UUID: {belief_id}", err=True)
            raise SystemExit(1) from None

        belief = beliefs_svc.get_belief(bid)
        if belief is None:
            click.echo(f"Belief not found: {belief_id}", err=True)
            raise SystemExit(1)

        new_conf = min(1.0, belief.confidence + CONFIDENCE_STEP)
        beliefs_svc.update_confidence(bid, new_conf)
        signals.emit("belief_confirmed", {"belief_id": str(bid)})
        click.echo(f"Belief confirmed. Confidence: {belief.confidence:.2f} -> {new_conf:.2f}")
    finally:
        db.close()


@cli.command()
@click.argument("belief_id")
@click.pass_context
def refute(ctx: click.Context, belief_id: str) -> None:
    """Refute a belief -- reduce its confidence."""
    db, _notes, signals, _agent, edges_svc, beliefs_svc, _vs, _audit = _get_services(
        ctx.obj["db_path"]
    )
    try:
        try:
            bid = uuid.UUID(belief_id)
        except ValueError:
            click.echo(f"Error: invalid UUID: {belief_id}", err=True)
            raise SystemExit(1) from None

        belief = beliefs_svc.get_belief(bid)
        if belief is None:
            click.echo(f"Belief not found: {belief_id}", err=True)
            raise SystemExit(1)

        new_conf = max(0.0, belief.confidence - CONFIDENCE_STEP)
        beliefs_svc.update_confidence(bid, new_conf)
        signals.emit("belief_refuted", {"belief_id": str(bid)})
        click.echo(f"Belief refuted. Confidence: {belief.confidence:.2f} -> {new_conf:.2f}")
    finally:
        db.close()


@cli.command()
@click.argument("source_id")
@click.argument("level", type=click.Choice(["user", "trusted", "unknown"]))
@click.pass_context
def trust(ctx: click.Context, source_id: str, level: str) -> None:
    """Update trust level for a source."""
    db, notes_svc, signals, *_ = _get_services(ctx.obj["db_path"])
    try:
        try:
            sid = uuid.UUID(source_id)
        except ValueError:
            click.echo(f"Error: invalid UUID: {source_id}", err=True)
            raise SystemExit(1) from None

        try:
            notes_svc.update_source_trust(sid, TrustLabel(level))
        except ValueError as exc:
            click.echo(f"Error: {exc}", err=True)
            raise SystemExit(1) from None

        signals.emit(
            "source_trust_updated",
            {"source_id": str(sid), "new_level": level},
        )
        click.echo(f"Source {sid} trust updated to: {level}")
    finally:
        db.close()


@cli.command()
@click.pass_context
def report(ctx: click.Context) -> None:
    """Generate a status report of the knowledge base."""
    from second_brain.core.models import BeliefStatus, EntityType, RelType

    db, notes_svc, _signals, _agent, edges_svc, beliefs_svc, _vs, _audit = _get_services(
        ctx.obj["db_path"]
    )
    try:
        # Summary counts
        all_notes = notes_svc.list_notes(limit=REPORT_QUERY_LIMIT)
        click.echo("=== Knowledge Base Report ===")
        click.echo(f"Total notes: {len(all_notes)}")

        for status in BeliefStatus:
            beliefs = beliefs_svc.list_beliefs(status_filter=status, limit=REPORT_QUERY_LIMIT)
            if beliefs:
                click.echo(f"Beliefs [{status.value}]: {len(beliefs)}")

        # Active contradictions
        click.echo("\n--- Active Contradictions ---")
        challenged = beliefs_svc.list_beliefs(
            status_filter=BeliefStatus.CHALLENGED, limit=100
        )
        if challenged:
            for belief in challenged:
                edges = edges_svc.get_edges(
                    EntityType.BELIEF, belief.belief_id,
                    direction="incoming", rel_type=RelType.CONTRADICTS,
                )
                click.echo(
                    f"  {belief.claim_text} "
                    f"(confidence: {belief.confidence:.2f}, contradictions: {len(edges)})"
                )
        else:
            click.echo("  (none)")

        # Beliefs approaching decay threshold
        click.echo("\n--- Low Confidence Beliefs ---")
        active = beliefs_svc.list_beliefs(status_filter=BeliefStatus.ACTIVE, limit=1000)
        low_conf = [b for b in active if b.confidence < LOW_CONFIDENCE_THRESHOLD]
        if low_conf:
            for belief in low_conf:
                click.echo(f"  {belief.claim_text} (confidence: {belief.confidence:.2f})")
        else:
            click.echo("  (none)")

        # Recently archived
        click.echo("\n--- Recently Archived ---")
        archived = beliefs_svc.list_beliefs(
            status_filter=BeliefStatus.ARCHIVED, limit=10
        )
        if archived:
            for belief in archived:
                click.echo(f"  {belief.claim_text}")
        else:
            click.echo("  (none)")
    finally:
        db.close()


@cli.command()
@click.argument("output_path", required=False)
@click.pass_context
def snapshot(ctx: click.Context, output_path: str | None) -> None:
    """Create a full database backup."""
    from second_brain.storage.sqlite import DEFAULT_DB_PATH

    db_path = ctx.obj["db_path"] or str(DEFAULT_DB_PATH)
    source = Path(db_path)
    if not source.exists():
        click.echo(f"Error: database not found at {db_path}", err=True)
        raise SystemExit(1)

    if output_path is None:
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        output_path = str(source.parent / f"brain_snapshot_{ts}.db")

    shutil.copy2(str(source), output_path)
    click.echo(f"Snapshot saved: {output_path}")


@cli.command()
@click.argument("snapshot_path")
@click.pass_context
def restore(ctx: click.Context, snapshot_path: str) -> None:
    """Restore database from a snapshot."""
    from second_brain.storage.sqlite import DEFAULT_DB_PATH

    snap = Path(snapshot_path)
    if not snap.exists():
        click.echo(f"Error: snapshot not found at {snapshot_path}", err=True)
        raise SystemExit(1)

    db_path = ctx.obj["db_path"] or str(DEFAULT_DB_PATH)
    target = Path(db_path)

    # Auto-snapshot current database before overwriting
    if target.exists():
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_path = target.parent / f"brain_pre_restore_{ts}.db"
        shutil.copy2(str(target), str(backup_path))
        click.echo(f"Current database backed up to: {backup_path}")

    shutil.copy2(str(snap), str(target))
    click.echo(f"Database restored from: {snapshot_path}")


@cli.command(name="run")
@click.option("--once", is_flag=True, default=True, help="Run a single scheduler tick.")
@click.pass_context
def run_agents(ctx: click.Context, once: bool) -> None:
    """Run all agents (scheduler tick)."""
    from second_brain.agents.challenger import ChallengerAgent
    from second_brain.agents.curator import CuratorAgent
    from second_brain.agents.synthesis import SynthesisAgent
    from second_brain.core.rules.lifecycle import auto_transition_beliefs
    from second_brain.runtime.scheduler import Scheduler

    db, notes_svc, signals, _agent, edges_svc, beliefs_svc, vs, audit = _get_services(
        ctx.obj["db_path"]
    )
    try:
        curator = CuratorAgent(notes_svc, beliefs_svc, edges_svc, signals, audit, vs)
        challenger = ChallengerAgent(beliefs_svc, edges_svc, signals)
        synthesis = SynthesisAgent(notes_svc, beliefs_svc, edges_svc, signals)

        scheduler = Scheduler()
        scheduler.register("curator", curator.run)
        scheduler.register("lifecycle", lambda: auto_transition_beliefs(beliefs_svc, edges_svc))
        scheduler.register("challenger", challenger.run)
        scheduler.register("synthesis", synthesis.run)

        results = scheduler.run_once()
        for name, result in results:
            click.echo(f"  {name}: {result}")
    finally:
        db.close()
