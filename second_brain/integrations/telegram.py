"""Telegram bot integration for Second Brain.

Any plain message is ingested as a note. Commands map to brain operations:
  /ask <query>     — evidence-grounded Q&A
  /search <query>  — full-text search
  /beliefs         — list beliefs
  /confirm <id>    — confirm a belief
  /refute <id>     — refute a belief
  /status          — system health
  /process         — run proactive cycle
  /help            — show commands
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from second_brain.agents.ingestion import IngestionAgent
from second_brain.core.models import BeliefStatus, ContentType
from second_brain.core.services.ask import AskPipeline
from second_brain.core.services.beliefs import BeliefService
from second_brain.core.services.notes import NoteService
from second_brain.core.services.reports import ReportService
from second_brain.core.services.signals import SignalService
from second_brain.runtime.dispatcher import Dispatcher
from second_brain.storage.migrations.runner import ensure_schema
from second_brain.storage.sqlite import Database

logger = logging.getLogger(__name__)

# ── Database helper ──────────────────────────────────────────────────────────

_DB_PATH: Path | None = None


def _get_db() -> Database:
    path = _DB_PATH or Path(os.environ.get(
        "BRAIN_DB_PATH",
        str(Path.home() / ".second-brain" / "brain.db"),
    ))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(path)
    ensure_schema(db)
    return db


# ── Handlers ─────────────────────────────────────────────────────────────────


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Second Brain connected.\n\n"
        "Send any message to capture it as a note.\n"
        "Use /help to see all commands."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Commands:\n"
        "  /ask <query> — ask a question (evidence-grounded)\n"
        "  /search <query> — full-text search\n"
        "  /beliefs — list beliefs\n"
        "  /confirm <id> — confirm a belief\n"
        "  /refute <id> — refute a belief\n"
        "  /status — system health\n"
        "  /process — run proactive cycle\n"
        "  /help — this message\n\n"
        "Any other message is captured as a note."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ingest any plain text message as a note."""
    text = update.message.text
    if not text or not text.strip():
        return

    db = _get_db()
    try:
        agent = IngestionAgent(db)
        result = agent.ingest(
            content=text,
            content_type=ContentType.TEXT,
            locator=f"telegram:{update.effective_user.id}",
        )
        tags = ", ".join(result["tags"]) if result["tags"] else "none"
        entities = ", ".join(result["entities"]) if result["entities"] else "none"
        await update.message.reply_text(
            f"Noted.\n"
            f"  id: {result['note_id'][:8]}\n"
            f"  tags: {tags}\n"
            f"  entities: {entities}"
        )
    finally:
        db.close()


async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Usage: /ask <your question>")
        return

    db = _get_db()
    try:
        pipeline = AskPipeline(db)
        answer = pipeline.ask(query)

        if not answer.evidence.has_evidence:
            await update.message.reply_text("No relevant evidence found.")
            return

        text = answer.summary
        citations = (
            f"\n\nCitations: {len(answer.cited_note_ids)} notes, "
            f"{len(answer.cited_belief_ids)} beliefs"
        )
        # Telegram message limit is 4096 chars
        if len(text) + len(citations) > 4000:
            text = text[:4000 - len(citations)] + "..."
        await update.message.reply_text(text + citations)
    finally:
        db.close()


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Usage: /search <query>")
        return

    db = _get_db()
    try:
        svc = NoteService(db)
        results = svc.search_notes(query, limit=10)

        if not results:
            await update.message.reply_text("No results found.")
            return

        lines = [f"Search: '{query}' ({len(results)} results)\n"]
        for note in results:
            snippet = note.content[:100] + ("..." if len(note.content) > 100 else "")
            tags = ", ".join(note.tags) if note.tags else ""
            lines.append(f"[{note.note_id[:8]}] {snippet}")
            if tags:
                lines.append(f"  tags: {tags}")
        await update.message.reply_text("\n".join(lines))
    finally:
        db.close()


async def cmd_beliefs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _get_db()
    try:
        svc = BeliefService(db)

        status_filter = None
        if context.args:
            try:
                status_filter = BeliefStatus(context.args[0])
            except ValueError:
                pass

        results = svc.list_beliefs(status=status_filter, limit=20)

        if not results:
            await update.message.reply_text("No beliefs yet.")
            return

        lines = [f"Beliefs ({len(results)} shown)\n"]
        for b in results:
            lines.append(
                f"[{b.belief_id[:8]}] {b.status.value} ({b.confidence:.2f}) "
                f"{b.claim_text[:60]}"
            )
        await update.message.reply_text("\n".join(lines))
    finally:
        db.close()


async def cmd_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /confirm <belief_id>")
        return

    belief_id = context.args[0]
    db = _get_db()
    try:
        svc = BeliefService(db)
        signals = SignalService(db)

        belief = _resolve_belief(svc, belief_id)
        if belief is None:
            await update.message.reply_text(f"Belief not found: {belief_id}")
            return

        new_conf = min(1.0, belief.confidence + 0.2)
        svc.update_confidence(belief.belief_id, new_conf)

        if belief.status == BeliefStatus.PROPOSED and new_conf >= 0.6:
            svc.transition(belief.belief_id, BeliefStatus.ACTIVE)

        signals.emit("belief_confirmed", {"belief_id": belief.belief_id})

        await update.message.reply_text(
            f"Confirmed: {belief.claim_text[:60]}\n"
            f"  confidence: {belief.confidence:.2f} → {new_conf:.2f}"
        )
    finally:
        db.close()


async def cmd_refute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /refute <belief_id>")
        return

    belief_id = context.args[0]
    db = _get_db()
    try:
        svc = BeliefService(db)
        signals = SignalService(db)

        belief = _resolve_belief(svc, belief_id)
        if belief is None:
            await update.message.reply_text(f"Belief not found: {belief_id}")
            return

        new_conf = max(0.0, belief.confidence - 0.3)
        svc.update_confidence(belief.belief_id, new_conf)

        if belief.status == BeliefStatus.ACTIVE:
            svc.transition(belief.belief_id, BeliefStatus.CHALLENGED)

        signals.emit("belief_refuted", {"belief_id": belief.belief_id})

        await update.message.reply_text(
            f"Refuted: {belief.claim_text[:60]}\n"
            f"  confidence: {belief.confidence:.2f} → {new_conf:.2f}"
        )
    finally:
        db.close()


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _get_db()
    try:
        r = ReportService(db).generate_health_report()
        belief_lines = "\n".join(f"  {k}: {v}" for k, v in r.belief_counts.items())
        await update.message.reply_text(
            f"Brain Status\n"
            f"  Notes: {r.note_count}\n"
            f"  Sources: {r.source_count}\n"
            f"  Edges: {r.edge_count}\n"
            f"  Contradictions: {r.contradiction_count}\n"
            f"  Pending signals: {r.pending_signal_count}\n"
            f"  Audit entries: {r.audit_entry_count}\n"
            f"Beliefs:\n{belief_lines}"
        )
    finally:
        db.close()


async def cmd_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _get_db()
    try:
        dispatcher = Dispatcher(db)
        results = dispatcher.run_full_cycle()

        sig_count = len(results.get("signal_results", []))
        challenge_count = len(results.get("challenger_results", []))
        synth_count = len(results.get("synthesis_results", []))

        await update.message.reply_text(
            f"Cycle complete:\n"
            f"  Signals processed: {sig_count}\n"
            f"  Contradictions found: {challenge_count}\n"
            f"  Beliefs synthesized: {synth_count}"
        )
    finally:
        db.close()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _resolve_belief(svc: BeliefService, belief_id: str):
    """Resolve a belief by full ID or prefix."""
    belief = svc.get_belief(belief_id)
    if belief is not None:
        return belief
    all_beliefs = svc.list_beliefs(limit=1000)
    matches = [b for b in all_beliefs if b.belief_id.startswith(belief_id)]
    return matches[0] if len(matches) == 1 else None


# ── Bot builder ──────────────────────────────────────────────────────────────


def build_app(token: str, db_path: Path | None = None) -> Application:
    """Build and return a configured Telegram Application (does not start it)."""
    global _DB_PATH
    if db_path:
        _DB_PATH = db_path

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("beliefs", cmd_beliefs))
    app.add_handler(CommandHandler("confirm", cmd_confirm))
    app.add_handler(CommandHandler("refute", cmd_refute))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("process", cmd_process))

    # Any non-command text message → ingest as note
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app


def run_bot(token: str, db_path: Path | None = None) -> None:
    """Build and run the bot (blocking, uses polling)."""
    application = build_app(token, db_path)
    logger.info("Starting Second Brain Telegram bot...")
    application.run_polling()
