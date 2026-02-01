"""Scheduler — periodic tick for the proactive pipeline.

Per design.md Section 7.3:
  Scheduler tick → CuratorAgent → ChallengerAgent → SynthesisAgent → Reports
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from second_brain.agents.challenger import ChallengerAgent
from second_brain.agents.curator import CuratorAgent
from second_brain.agents.synthesis import SynthesisAgent
from second_brain.runtime.dispatcher import Dispatcher
from second_brain.storage.sqlite import Database


class Scheduler:
    def __init__(self, db: Database, interval_seconds: int = 300):
        self.db = db
        self.interval = interval_seconds
        self.dispatcher = Dispatcher(db)
        self.curator = CuratorAgent(db)
        self._running = False
        self._thread: threading.Thread | None = None

    def tick(self) -> dict:
        """Execute one proactive cycle.

        Order per design spec:
        1. CuratorAgent (archive/merge/distill)
        2. ChallengerAgent (contradiction detection)
        3. SynthesisAgent (new belief generation)
        4. Process any remaining signals
        """
        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "curator": [],
            "challenger": [],
            "synthesis": [],
            "dispatch": [],
        }

        results["curator"] = self.curator.run()
        results["challenger"] = ChallengerAgent(self.db).run()
        results["synthesis"] = SynthesisAgent(self.db).run()
        results["dispatch"] = self.dispatcher.process_pending()

        return results

    def start(self) -> None:
        """Start the scheduler in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while self._running:
            self.tick()
            time.sleep(self.interval)
