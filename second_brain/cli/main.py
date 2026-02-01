"""CLI entry point — full Typer CLI for Second Brain."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from second_brain.agents.ingestion import IngestionAgent
from second_brain.core.models import BeliefStatus, ContentType
from second_brain.core.services.ask import AskPipeline
from second_brain.core.services.beliefs import BeliefService
from second_brain.core.services.notes import NoteService
from second_brain.core.services.reports import ReportService
from second_brain.core.services.signals import SignalService
from second_brain.runtime.dispatcher import Dispatcher
from second_brain.storage.migrations.runner import ensure_schema
from second_brain.storage.snapshot import create_snapshot, list_snapshots, restore_snapshot
from second_brain.storage.sqlite import Database

app = typer.Typer(
    name="brain",
    help="Second Brain — local cognitive substrate",
    no_args_is_help=True,
)
console = Console()

# Default DB path — can be overridden via env var
_DB_PATH = Path(typer.get_app_dir("second-brain")) / "brain.db"


def _get_db() -> Database:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = Database(_DB_PATH)
    ensure_schema(db)
    return db


@app.command()
def add(
    content: str = typer.Argument(None, help="Text content to add (or pipe via stdin)"),
    content_type: str = typer.Option("text", "--type", "-t", help="Content type: text, markdown, code"),
    tags: str = typer.Option("", "--tags", help="Comma-separated extra tags"),
):
    """Add a new note to the brain."""
    # Support piped input
    if content is None:
        if not sys.stdin.isatty():
            content = sys.stdin.read().strip()
        else:
            console.print("[red]Error:[/red] Provide content as argument or pipe via stdin.")
            raise typer.Exit(1)

    if not content:
        console.print("[red]Error:[/red] Empty content.")
        raise typer.Exit(1)

    db = _get_db()
    agent = IngestionAgent(db)

    extra_tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    ct = ContentType(content_type)

    result = agent.ingest(content=content, content_type=ct, extra_tags=extra_tags)

    console.print(Panel(
        f"[green]Note added[/green]\n"
        f"  note_id: {result['note_id']}\n"
        f"  hash:    {result['content_hash'][:16]}...\n"
        f"  tags:    {result['tags']}\n"
        f"  entities:{result['entities']}",
        title="Ingested",
    ))
    db.close()


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query (FTS5)"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
):
    """Search notes using full-text search."""
    db = _get_db()
    svc = NoteService(db)
    results = svc.search_notes(query, limit=limit)

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        db.close()
        return

    table = Table(title=f"Search: '{query}' ({len(results)} results)")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Created", max_width=20)
    table.add_column("Content", max_width=60)
    table.add_column("Tags")

    for note in results:
        snippet = note.content[:80] + ("..." if len(note.content) > 80 else "")
        table.add_row(
            note.note_id[:8],
            str(note.created_at)[:19],
            snippet,
            ", ".join(note.tags) if note.tags else "-",
        )

    console.print(table)
    db.close()


@app.command()
def show(
    note_id: str = typer.Argument(..., help="Note ID (full or prefix)"),
):
    """Show details of a specific note."""
    db = _get_db()
    svc = NoteService(db)

    # Support prefix matching
    note = svc.get_note(note_id)
    if note is None:
        # Try prefix match
        all_notes = svc.list_notes(limit=1000)
        matches = [n for n in all_notes if n.note_id.startswith(note_id)]
        if len(matches) == 1:
            note = matches[0]
        elif len(matches) > 1:
            console.print(f"[yellow]Ambiguous prefix, {len(matches)} matches.[/yellow]")
            db.close()
            return
        else:
            console.print(f"[red]Note not found: {note_id}[/red]")
            db.close()
            return

    console.print(Panel(
        f"[bold]note_id:[/bold]      {note.note_id}\n"
        f"[bold]created_at:[/bold]   {note.created_at}\n"
        f"[bold]content_type:[/bold] {note.content_type.value}\n"
        f"[bold]source_id:[/bold]    {note.source_id}\n"
        f"[bold]content_hash:[/bold] {note.content_hash}\n"
        f"[bold]tags:[/bold]         {note.tags}\n"
        f"[bold]entities:[/bold]     {note.entities}\n"
        f"\n{note.content}",
        title="Note Detail",
    ))
    db.close()


@app.command(name="list")
def list_notes(
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
):
    """List recent notes."""
    db = _get_db()
    svc = NoteService(db)
    results = svc.list_notes(limit=limit)

    if not results:
        console.print("[yellow]No notes yet.[/yellow]")
        db.close()
        return

    table = Table(title=f"Notes ({len(results)} shown)")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Created", max_width=20)
    table.add_column("Type", max_width=10)
    table.add_column("Content", max_width=50)
    table.add_column("Tags")

    for note in results:
        snippet = note.content[:60] + ("..." if len(note.content) > 60 else "")
        table.add_row(
            note.note_id[:8],
            str(note.created_at)[:19],
            note.content_type.value,
            snippet,
            ", ".join(note.tags) if note.tags else "-",
        )

    console.print(table)
    db.close()


@app.command()
def ask(
    query: str = typer.Argument(..., help="Question to ask the brain"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max evidence items"),
):
    """Ask a question — answers grounded in stored evidence."""
    db = _get_db()
    pipeline = AskPipeline(db)
    answer = pipeline.ask(query, limit=limit)

    if not answer.evidence.has_evidence:
        console.print("[yellow]No relevant evidence found.[/yellow]")
        db.close()
        return

    console.print(Panel(answer.summary, title=f"Answer: {query}"))

    if answer.cited_note_ids:
        console.print(
            f"\n[dim]Citations: {len(answer.cited_note_ids)} notes, "
            f"{len(answer.cited_belief_ids)} beliefs[/dim]"
        )
    db.close()


@app.command()
def beliefs(
    status: str = typer.Option(None, "--status", "-s", help="Filter by status"),
    limit: int = typer.Option(20, "--limit", "-n"),
):
    """List beliefs in the system."""
    db = _get_db()
    svc = BeliefService(db)

    filter_status = BeliefStatus(status) if status else None
    results = svc.list_beliefs(status=filter_status, limit=limit)

    if not results:
        console.print("[yellow]No beliefs yet.[/yellow]")
        db.close()
        return

    table = Table(title=f"Beliefs ({len(results)} shown)")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Status", max_width=12)
    table.add_column("Conf", max_width=6)
    table.add_column("Claim", max_width=60)
    table.add_column("Agent", max_width=12)

    for b in results:
        style = {
            "active": "green",
            "proposed": "blue",
            "challenged": "yellow",
            "deprecated": "red",
            "archived": "dim",
        }.get(b.status.value, "")

        table.add_row(
            b.belief_id[:8],
            f"[{style}]{b.status.value}[/{style}]",
            f"{b.confidence:.2f}",
            b.claim_text[:60] + ("..." if len(b.claim_text) > 60 else ""),
            b.derived_from_agent or "-",
        )

    console.print(table)
    db.close()


@app.command()
def confirm(
    belief_id: str = typer.Argument(..., help="Belief ID to confirm"),
):
    """Confirm a belief — boosts confidence and emits belief_confirmed signal."""
    db = _get_db()
    svc = BeliefService(db)
    signals = SignalService(db)

    belief = svc.get_belief(belief_id)
    if belief is None:
        # Try prefix match
        all_beliefs = svc.list_beliefs(limit=1000)
        matches = [b for b in all_beliefs if b.belief_id.startswith(belief_id)]
        if len(matches) == 1:
            belief = matches[0]
        else:
            console.print(f"[red]Belief not found: {belief_id}[/red]")
            db.close()
            return

    new_conf = min(1.0, belief.confidence + 0.2)
    svc.update_confidence(belief.belief_id, new_conf)

    # Activate if proposed and confidence meets threshold
    if belief.status == BeliefStatus.PROPOSED and new_conf >= 0.6:
        svc.transition(belief.belief_id, BeliefStatus.ACTIVE)

    signals.emit("belief_confirmed", {"belief_id": belief.belief_id})

    console.print(
        f"[green]Confirmed:[/green] {belief.claim_text[:60]}\n"
        f"  confidence: {belief.confidence:.2f} → {new_conf:.2f}"
    )
    db.close()


@app.command()
def refute(
    belief_id: str = typer.Argument(..., help="Belief ID to refute"),
):
    """Refute a belief — reduces confidence and emits belief_refuted signal."""
    db = _get_db()
    svc = BeliefService(db)
    signals = SignalService(db)

    belief = svc.get_belief(belief_id)
    if belief is None:
        all_beliefs = svc.list_beliefs(limit=1000)
        matches = [b for b in all_beliefs if b.belief_id.startswith(belief_id)]
        if len(matches) == 1:
            belief = matches[0]
        else:
            console.print(f"[red]Belief not found: {belief_id}[/red]")
            db.close()
            return

    new_conf = max(0.0, belief.confidence - 0.3)
    svc.update_confidence(belief.belief_id, new_conf)

    # Challenge if active
    if belief.status == BeliefStatus.ACTIVE:
        svc.transition(belief.belief_id, BeliefStatus.CHALLENGED)

    signals.emit("belief_refuted", {"belief_id": belief.belief_id})

    console.print(
        f"[red]Refuted:[/red] {belief.claim_text[:60]}\n"
        f"  confidence: {belief.confidence:.2f} → {new_conf:.2f}"
    )
    db.close()


@app.command()
def status():
    """Show system health and status report."""
    db = _get_db()
    report = ReportService(db).generate_health_report()

    table = Table(title="Brain Status")
    table.add_column("Metric", style="bold")
    table.add_column("Value")

    table.add_row("Notes", str(report.note_count))
    table.add_row("Sources", str(report.source_count))
    table.add_row("Edges", str(report.edge_count))
    table.add_row("Audit entries", str(report.audit_entry_count))
    table.add_row("Pending signals", str(report.pending_signal_count))
    table.add_row("Contradictions", str(report.contradiction_count))

    for status_name, count in report.belief_counts.items():
        table.add_row(f"Beliefs ({status_name})", str(count))

    console.print(table)
    db.close()


@app.command()
def snapshot():
    """Create a snapshot backup of the database."""
    db = _get_db()
    path = create_snapshot(_DB_PATH)
    console.print(f"[green]Snapshot created:[/green] {path}")
    db.close()


@app.command()
def restore(
    snapshot_path: str = typer.Argument(None, help="Path to snapshot file (or pick latest)"),
):
    """Restore the database from a snapshot."""
    if snapshot_path:
        path = Path(snapshot_path)
    else:
        snapshots = list_snapshots(_DB_PATH)
        if not snapshots:
            console.print("[red]No snapshots found.[/red]")
            return
        path = snapshots[0]
        console.print(f"Restoring latest: {path.name}")

    restore_snapshot(path, _DB_PATH)
    console.print(f"[green]Restored from:[/green] {path}")


@app.command()
def report():
    """Generate a detailed health report."""
    db = _get_db()
    r = ReportService(db).generate_health_report()

    console.print(Panel(
        f"[bold]Generated:[/bold] {r.generated_at}\n\n"
        f"[bold]Notes:[/bold]         {r.note_count}\n"
        f"[bold]Sources:[/bold]       {r.source_count}\n"
        f"[bold]Total beliefs:[/bold] {r.total_beliefs}\n"
        + "".join(f"  {k}: {v}\n" for k, v in r.belief_counts.items())
        + f"\n[bold]Edges:[/bold]         {r.edge_count}\n"
        f"[bold]Contradictions:[/bold] {r.contradiction_count}\n"
        f"[bold]Pending signals:[/bold]{r.pending_signal_count}\n"
        f"[bold]Audit entries:[/bold]  {r.audit_entry_count}",
        title="Health Report",
    ))
    db.close()


@app.command()
def process():
    """Run one proactive cycle (dispatch signals, run agents)."""
    db = _get_db()
    dispatcher = Dispatcher(db)
    results = dispatcher.run_full_cycle()

    sig_count = len(results.get("signal_results", []))
    challenge_count = len(results.get("challenger_results", []))
    synth_count = len(results.get("synthesis_results", []))

    console.print(
        f"[green]Cycle complete:[/green]\n"
        f"  Signals processed: {sig_count}\n"
        f"  Contradictions found: {challenge_count}\n"
        f"  Beliefs synthesized: {synth_count}"
    )
    db.close()


if __name__ == "__main__":
    app()
