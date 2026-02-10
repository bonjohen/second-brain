"""CLI entry point for Second Brain."""

from __future__ import annotations

import sys
import uuid

import click

from second_brain.core.models import ContentType, SourceKind


def _get_services(db_path: str | None = None):
    """Construct and return (Database, NoteService, SignalService, IngestionAgent)."""
    from second_brain.agents.ingestion import IngestionAgent
    from second_brain.core.services.audit import AuditService
    from second_brain.core.services.notes import NoteService
    from second_brain.core.services.signals import SignalService
    from second_brain.storage.sqlite import Database

    db = Database(db_path) if db_path else Database()
    audit = AuditService(db)
    signals = SignalService(db)
    notes = NoteService(db, audit)
    agent = IngestionAgent(notes, signals)
    return db, notes, signals, agent


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

    db, _notes, _signals, agent = _get_services(ctx.obj["db_path"])
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
    db, notes_svc, _, _ = _get_services(ctx.obj["db_path"])
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
    db, notes_svc, _, _ = _get_services(ctx.obj["db_path"])
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
