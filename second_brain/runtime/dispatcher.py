"""Signal dispatcher -- routes signals to registered agent handlers."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from second_brain.core.models import Signal
from second_brain.core.services.signals import SignalService

logger = logging.getLogger(__name__)

# Handler type: a callable that takes a Signal and returns anything
SignalHandler = Callable[[Signal], Any]


class Dispatcher:
    """Polls unprocessed signals and routes them to registered handlers.

    Handlers are registered per signal type. Multiple handlers per type are supported.
    On error, the signal is NOT marked as processed (retry on next poll).
    """

    def __init__(self, signal_service: SignalService) -> None:
        self._signals = signal_service
        self._handlers: dict[str, list[SignalHandler]] = {}

    def register(self, signal_type: str, handler: SignalHandler) -> None:
        """Register a handler for a signal type."""
        self._handlers.setdefault(signal_type, []).append(handler)

    def dispatch_once(self) -> int:
        """Poll and dispatch all unprocessed signals once.

        Returns the number of signals successfully processed.
        """
        processed_count = 0
        signals = self._signals.get_unprocessed()

        for signal in signals:
            handlers = self._handlers.get(signal.type, [])
            if not handlers:
                # No handler registered -- mark processed to avoid infinite polling
                self._signals.mark_processed(signal.signal_id)
                processed_count += 1
                continue

            try:
                for handler in handlers:
                    handler(signal)
                self._signals.mark_processed(signal.signal_id)
                processed_count += 1
            except Exception:
                # Do not mark as processed on error -- will retry on next poll
                logger.exception(
                    "Handler failed for signal %s (type=%s)", signal.signal_id, signal.type
                )

        return processed_count
