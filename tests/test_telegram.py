"""Tests for the Telegram bot integration — handler logic only, no network."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from second_brain.integrations import telegram as tg
from second_brain.storage.migrations.runner import ensure_schema
from second_brain.storage.sqlite import Database


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    ensure_schema(db)
    tg._DB_PATH = db_path
    yield db
    db.close()
    tg._DB_PATH = None


def _make_update(text: str, args: list[str] | None = None):
    """Create a mock Telegram Update with a message."""
    update = MagicMock(spec_set=["message", "effective_user"])
    update.message = AsyncMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 12345

    context = MagicMock()
    context.args = args or []
    return update, context


# ── Message ingestion ────────────────────────────────────────────────────────


class TestMessageIngestion:
    @pytest.mark.asyncio
    async def test_plain_message_ingested(self, db):
        update, ctx = _make_update("Python is great for #datascience")
        await tg.handle_message(update, ctx)

        update.message.reply_text.assert_called_once()
        reply = update.message.reply_text.call_args[0][0]
        assert "Noted." in reply
        assert "datascience" in reply

    @pytest.mark.asyncio
    async def test_empty_message_ignored(self, db):
        update, ctx = _make_update("")
        await tg.handle_message(update, ctx)
        update.message.reply_text.assert_not_called()


# ── Commands ─────────────────────────────────────────────────────────────────


class TestCommands:
    @pytest.mark.asyncio
    async def test_start(self, db):
        update, ctx = _make_update("/start")
        await tg.cmd_start(update, ctx)
        update.message.reply_text.assert_called_once()
        assert "connected" in update.message.reply_text.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_help(self, db):
        update, ctx = _make_update("/help")
        await tg.cmd_help(update, ctx)
        reply = update.message.reply_text.call_args[0][0]
        assert "/ask" in reply
        assert "/search" in reply

    @pytest.mark.asyncio
    async def test_status(self, db):
        update, ctx = _make_update("/status")
        await tg.cmd_status(update, ctx)
        reply = update.message.reply_text.call_args[0][0]
        assert "Notes:" in reply

    @pytest.mark.asyncio
    async def test_ask_no_query(self, db):
        update, ctx = _make_update("/ask")
        await tg.cmd_ask(update, ctx)
        reply = update.message.reply_text.call_args[0][0]
        assert "Usage" in reply

    @pytest.mark.asyncio
    async def test_ask_with_query(self, db):
        # Ingest a note first
        ingest_update, ingest_ctx = _make_update("Rust is a systems programming language")
        await tg.handle_message(ingest_update, ingest_ctx)

        update, ctx = _make_update("/ask Rust", ["Rust"])
        await tg.cmd_ask(update, ctx)
        update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_no_query(self, db):
        update, ctx = _make_update("/search")
        await tg.cmd_search(update, ctx)
        assert "Usage" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_search_with_results(self, db):
        ingest_update, ingest_ctx = _make_update("Quantum computing is advancing rapidly")
        await tg.handle_message(ingest_update, ingest_ctx)

        update, ctx = _make_update("/search quantum", ["quantum"])
        await tg.cmd_search(update, ctx)
        reply = update.message.reply_text.call_args[0][0]
        assert "quantum" in reply.lower() or "Quantum" in reply

    @pytest.mark.asyncio
    async def test_beliefs_empty(self, db):
        update, ctx = _make_update("/beliefs")
        await tg.cmd_beliefs(update, ctx)
        assert "No beliefs" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_process(self, db):
        update, ctx = _make_update("/process")
        await tg.cmd_process(update, ctx)
        reply = update.message.reply_text.call_args[0][0]
        assert "Cycle complete" in reply

    @pytest.mark.asyncio
    async def test_confirm_missing_id(self, db):
        update, ctx = _make_update("/confirm")
        await tg.cmd_confirm(update, ctx)
        assert "Usage" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_refute_missing_id(self, db):
        update, ctx = _make_update("/refute")
        await tg.cmd_refute(update, ctx)
        assert "Usage" in update.message.reply_text.call_args[0][0]


# ── App builder ──────────────────────────────────────────────────────────────


class TestBuildApp:
    def test_build_app_registers_handlers(self, db):
        app = tg.build_app("fake-token-for-testing", db_path=db.path)
        # Should have handlers registered (commands + message handler)
        assert len(app.handlers[0]) > 0
