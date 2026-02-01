"""Dispatcher — consumes signals and routes them to the correct agent.

Per design.md Section 7.3: Scheduler tick → CuratorAgent → ChallengerAgent → SynthesisAgent
"""

from __future__ import annotations

from second_brain.agents.challenger import ChallengerAgent
from second_brain.agents.synthesis import SynthesisAgent
from second_brain.core.services.signals import SignalService
from second_brain.storage.sqlite import Database


# Signal-to-agent routing table
_SIGNAL_ROUTES = {
    "new_note": ["synthesis", "challenger"],
    "belief_proposed": ["challenger"],
    "belief_confirmed": [],
    "belief_refuted": [],
    "belief_challenged": [],
}


class Dispatcher:
    def __init__(self, db: Database):
        self.db = db
        self.signals = SignalService(db)
        self.synthesis = SynthesisAgent(db)
        self.challenger = ChallengerAgent(db)

    def process_pending(self) -> list[dict]:
        """Process all pending signals, routing to appropriate agents."""
        results = []
        pending = self.signals.consume_pending(limit=100)

        for signal in pending:
            routes = _SIGNAL_ROUTES.get(signal.type, [])
            for agent_name in routes:
                agent_results = self._dispatch_to_agent(agent_name, signal)
                results.extend(agent_results)
            self.signals.mark_processed(signal.signal_id)

        return results

    def _dispatch_to_agent(self, agent_name: str, signal) -> list[dict]:
        if agent_name == "synthesis":
            note_id = signal.payload.get("note_id")
            if note_id:
                return self.synthesis.run(note_ids=[note_id])
        elif agent_name == "challenger":
            return self.challenger.run()
        return []

    def run_full_cycle(self) -> dict:
        """Run a full proactive cycle: process signals, then run all agents."""
        signal_results = self.process_pending()
        challenger_results = self.challenger.run()
        synthesis_results = self.synthesis.run()

        return {
            "signal_results": signal_results,
            "challenger_results": challenger_results,
            "synthesis_results": synthesis_results,
        }
