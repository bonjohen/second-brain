"""Scheduler -- runs agents on a configurable tick interval."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# An agent step: a callable that takes no args and returns anything
AgentStep = Callable[[], Any]


class Scheduler:
    """Invokes registered agents in order on each tick.

    Supports run-once mode (single tick) and continuous mode (loop with interval).
    Agent order: Curator -> Challenger -> Synthesis (as per PDR Section 7.3).
    """

    def __init__(self, tick_interval: float = 60.0) -> None:
        self._tick_interval = tick_interval
        self._steps: list[tuple[str, AgentStep]] = []
        self._stop_event = threading.Event()
        self.failure_counts: dict[str, int] = {}

    def register(self, name: str, step: AgentStep) -> None:
        """Register an agent step to run on each tick."""
        self._steps.append((name, step))

    def tick(self) -> list[tuple[str, Any]]:
        """Run all registered agent steps in order once.

        Returns list of (name, result) for each step.
        """
        results: list[tuple[str, Any]] = []
        for name, step in self._steps:
            try:
                result = step()
                results.append((name, result))
                logger.info("Step '%s' completed: %s", name, result)
            except Exception:
                self.failure_counts[name] = self.failure_counts.get(name, 0) + 1
                logger.exception(
                    "Step '%s' failed (total failures: %d)", name, self.failure_counts[name]
                )
                results.append((name, None))
        return results

    def run_once(self) -> list[tuple[str, Any]]:
        """Run a single tick (for CLI invocation)."""
        return self.tick()

    def run_continuous(self, max_ticks: int | None = None) -> None:
        """Run ticks in a loop with configured interval.

        Args:
            max_ticks: If set, stop after this many ticks. None = run until stopped.
        """
        self._stop_event.clear()
        ticks_done = 0
        while not self._stop_event.is_set():
            self.tick()
            ticks_done += 1
            if max_ticks is not None and ticks_done >= max_ticks:
                break
            self._stop_event.wait(self._tick_interval)

    def stop(self) -> None:
        """Signal the continuous loop to stop."""
        self._stop_event.set()
