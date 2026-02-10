"""CLI entry point for Second Brain."""

from __future__ import annotations

import sys
import uuid

import click

from second_brain.core.models import ContentType, SourceKind


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
        pass

    agent = IngestionAgent(notes, signals, vector_store=vector_store)
    return db, notes, signals, agent, edges, beliefs, vector_store


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
    db.close()


@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=10, help="Max results.")
@click.pass_context
def search(ctx: click.Context, query: str, limit: int) -> None:
    """Search notes by keyword (FTS5)."""
    db, notes_svc, *_ = _get_services(ctx.obj["db_path"])
    results = notes_svc.search_notes(query)[:limit]
    if not results:
        click.echo("No results found.")
    else:
        for note in results:
            snippet = note.content[:120].replace("\n", " ")
            click.echo(f"[{note.note_id}] {snippet}")
            if note.tags:
                click.echo(f"  tags: {', '.join(note.tags)}")
    db.close()


@cli.command()
@click.argument("note_id")
@click.pass_context
def show(ctx: click.Context, note_id: str) -> None:
    """Show a note by ID."""
    db, notes_svc, *_ = _get_services(ctx.obj["db_path"])
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
    db.close()


@cli.command()
@click.argument("question")
@click.option("--top-k", "-k", default=5, help="Number of results to consider.")
@click.pass_context
def ask(ctx: click.Context, question: str, top_k: int) -> None:
    """Ask a question and get an answer with evidence and beliefs."""
    db, notes_svc, _signals, _agent, edges_svc, beliefs_svc, vector_store = _get_services(
        ctx.obj["db_path"]
    )

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
            pass  # graceful fallback if embeddings not available

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
        db.close()
        return

    # Evidence notes
    if evidence:
        click.echo("=== Evidence Notes ===")
        for i, note in enumerate(evidence, 1):
            snippet = note.content[:200].replace("\n", " ")
            click.echo(f"  [{i}] ({note.note_id}) {snippet}")
            if note.tags:
                click.echo(f"      tags: {', '.join(note.tags)}")

    # Related beliefs
    if related_beliefs:
        click.echo("\n=== Related Beliefs ===")
        for belief in related_beliefs:
            click.echo(
                f"  - [{belief.status.value}] (confidence: {belief.confidence:.2f}) "
                f"{belief.claim_text}"
            )

    # Template-based cited answer
    click.echo("\n=== Answer ===")
    click.echo(f"Based on {len(evidence)} evidence note(s):")
    for i, note in enumerate(evidence, 1):
        first_line = note.content.split("\n")[0][:100]
        click.echo(f"  [{i}] {first_line}")

    if related_beliefs:
        click.echo(f"\nRelated beliefs ({len(related_beliefs)}):")
        for belief in related_beliefs:
            click.echo(f"  - {belief.claim_text} (confidence: {belief.confidence:.2f})")

    db.close()
