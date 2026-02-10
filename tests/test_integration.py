"""Integration tests for the full signal pipeline.

Tests the flow: note ingestion -> synthesis -> challenger -> curator,
verifying that signals propagate correctly through the dispatcher and
that cross-agent interactions produce expected results.
"""

from second_brain.agents.challenger import ChallengerAgent
from second_brain.agents.ingestion import IngestionAgent
from second_brain.agents.synthesis import SynthesisAgent
from second_brain.core.models import BeliefStatus, EntityType, RelType
from second_brain.runtime.dispatcher import Dispatcher
from second_brain.runtime.scheduler import Scheduler


class TestSignalPipeline:
    """End-to-end tests for the signal-driven agent pipeline."""

    def test_ingestion_emits_new_note_signal(
        self, note_service, signal_service
    ):
        """IngestionAgent should emit a new_note signal after creating a note."""
        agent = IngestionAgent(note_service, signal_service)
        source, note = agent.ingest("Test content #python")

        signals = signal_service.get_unprocessed("new_note")
        assert len(signals) == 1
        assert signals[0].payload["note_id"] == str(note.note_id)

    def test_synthesis_consumes_new_note_signals(
        self, note_service, belief_service, edge_service, signal_service
    ):
        """SynthesisAgent should consume new_note signals and create beliefs
        when enough notes share a tag."""
        agent_ingest = IngestionAgent(note_service, signal_service)
        agent_synth = SynthesisAgent(
            note_service, belief_service, edge_service, signal_service
        )

        # Ingest two notes with a shared tag
        agent_ingest.ingest("First note about #machinelearning")
        agent_ingest.ingest("Second note about #machinelearning")

        # Synthesis processes the new_note signals
        belief_ids = agent_synth.run()

        assert len(belief_ids) >= 1
        # Verify belief was created
        belief = belief_service.get_belief(belief_ids[0])
        assert belief is not None
        assert "machinelearning" in belief.claim_text.lower()

    def test_synthesis_emits_belief_proposed_signal(
        self, note_service, belief_service, edge_service, signal_service
    ):
        """SynthesisAgent should emit belief_proposed signals."""
        agent_ingest = IngestionAgent(note_service, signal_service)
        agent_synth = SynthesisAgent(
            note_service, belief_service, edge_service, signal_service
        )

        agent_ingest.ingest("Note A about #databases")
        agent_ingest.ingest("Note B about #databases")

        agent_synth.run()

        signals = signal_service.get_unprocessed("belief_proposed")
        assert len(signals) >= 1
        assert "belief_id" in signals[0].payload

    def test_challenger_consumes_belief_proposed_signals(
        self, note_service, belief_service, edge_service, signal_service
    ):
        """ChallengerAgent should process belief_proposed signals and detect
        contradictions."""
        # Create two contradicting beliefs manually
        b1 = belief_service.create_belief(claim_text="python is fast")
        belief_service.update_belief_status(b1.belief_id, BeliefStatus.ACTIVE)

        b2 = belief_service.create_belief(claim_text="python is not fast")

        # Emit a belief_proposed signal for b2
        signal_service.emit(
            "belief_proposed", {"belief_id": str(b2.belief_id)}
        )

        challenger = ChallengerAgent(
            belief_service, edge_service, signal_service
        )
        challenged_ids = challenger.run()

        assert b1.belief_id in challenged_ids
        # b1 should now be challenged
        b1_updated = belief_service.get_belief(b1.belief_id)
        assert b1_updated.status == BeliefStatus.CHALLENGED

    def test_full_pipeline_ingestion_to_challenge(
        self, note_service, belief_service, edge_service, signal_service
    ):
        """Full pipeline: ingest notes -> synthesize beliefs -> challenge contradictions."""
        ingest = IngestionAgent(note_service, signal_service)
        synth = SynthesisAgent(
            note_service, belief_service, edge_service, signal_service
        )
        challenger = ChallengerAgent(
            belief_service, edge_service, signal_service
        )

        # Step 1: Ingest notes with shared tag
        ingest.ingest("Python performance is excellent #python")
        ingest.ingest("Python runs fast on modern hardware #python")

        # Step 2: Synthesis creates beliefs
        belief_ids = synth.run()
        assert len(belief_ids) >= 1

        # Step 3: Activate the synthesized belief
        for bid in belief_ids:
            belief_service.update_belief_status(bid, BeliefStatus.ACTIVE)

        # Step 4: Create a contradicting belief
        contra = belief_service.create_belief(
            claim_text="python is not fast"
        )
        signal_service.emit(
            "belief_proposed", {"belief_id": str(contra.belief_id)}
        )

        # Step 5: Challenger detects the contradiction
        challenger.run()

        # Verify the signals were consumed
        unprocessed = signal_service.get_unprocessed("belief_proposed")
        assert len(unprocessed) == 0

    def test_dispatcher_routes_signals_to_agents(
        self, note_service, belief_service, edge_service, signal_service
    ):
        """Dispatcher should route new_note signals to registered handlers."""
        dispatcher = Dispatcher(signal_service)

        # Track handler invocations
        handled_signals = []
        dispatcher.register(
            "new_note", lambda s: handled_signals.append(s.type)
        )

        # Emit a signal
        ingest = IngestionAgent(note_service, signal_service)
        ingest.ingest("Test note for dispatcher #test")

        # Dispatch
        count = dispatcher.dispatch_once()
        assert count == 1
        assert handled_signals == ["new_note"]

    def test_scheduler_runs_agents_in_order(
        self, note_service, belief_service, edge_service, signal_service, audit_service
    ):
        """Scheduler should run agent steps in registered order."""
        scheduler = Scheduler()
        execution_order = []

        scheduler.register(
            "synthesis",
            lambda: execution_order.append("synthesis"),
        )
        scheduler.register(
            "challenger",
            lambda: execution_order.append("challenger"),
        )

        scheduler.run_once()
        assert execution_order == ["synthesis", "challenger"]

    def test_supports_edges_created_by_synthesis(
        self, note_service, belief_service, edge_service, signal_service
    ):
        """Synthesis should create supports edges from notes to beliefs."""
        ingest = IngestionAgent(note_service, signal_service)
        synth = SynthesisAgent(
            note_service, belief_service, edge_service, signal_service
        )

        _, note1 = ingest.ingest("Rust is safe #rust")
        _, note2 = ingest.ingest("Rust prevents memory bugs #rust")

        belief_ids = synth.run()
        assert len(belief_ids) >= 1

        # Check supports edges
        edges = edge_service.get_edges(
            EntityType.BELIEF, belief_ids[0], direction="incoming"
        )
        supports = [e for e in edges if e.rel_type == RelType.SUPPORTS]
        assert len(supports) >= 2

    def test_contradicts_edges_created_by_challenger(
        self, note_service, belief_service, edge_service, signal_service
    ):
        """Challenger should create contradicts edges between conflicting beliefs."""
        b1 = belief_service.create_belief(claim_text="python is fast")
        belief_service.update_belief_status(b1.belief_id, BeliefStatus.ACTIVE)

        b2 = belief_service.create_belief(claim_text="python is not fast")
        signal_service.emit(
            "belief_proposed", {"belief_id": str(b2.belief_id)}
        )

        challenger = ChallengerAgent(
            belief_service, edge_service, signal_service
        )
        challenger.run()

        # Check for contradicts edges
        edges = edge_service.get_edges(
            EntityType.BELIEF, b1.belief_id, direction="incoming"
        )
        contradicts = [e for e in edges if e.rel_type == RelType.CONTRADICTS]
        assert len(contradicts) >= 1
