"""Tests for the signal dispatcher."""

from second_brain.runtime.dispatcher import Dispatcher


class TestDispatcher:
    def test_dispatch_no_signals(self, signal_service):
        dispatcher = Dispatcher(signal_service)
        assert dispatcher.dispatch_once() == 0

    def test_dispatch_routes_to_handler(self, signal_service):
        dispatcher = Dispatcher(signal_service)
        handled = []
        dispatcher.register("test_signal", lambda s: handled.append(s.type))

        signal_service.emit("test_signal", {"key": "value"})
        count = dispatcher.dispatch_once()

        assert count == 1
        assert handled == ["test_signal"]

    def test_dispatch_multiple_handlers(self, signal_service):
        dispatcher = Dispatcher(signal_service)
        results = []
        dispatcher.register("multi", lambda s: results.append("a"))
        dispatcher.register("multi", lambda s: results.append("b"))

        signal_service.emit("multi", {})
        dispatcher.dispatch_once()

        assert results == ["a", "b"]

    def test_dispatch_marks_processed(self, signal_service):
        dispatcher = Dispatcher(signal_service)
        dispatcher.register("mark_test", lambda s: None)

        signal_service.emit("mark_test", {})
        dispatcher.dispatch_once()

        unprocessed = signal_service.get_unprocessed("mark_test")
        assert len(unprocessed) == 0

    def test_dispatch_error_does_not_mark_processed(self, signal_service):
        dispatcher = Dispatcher(signal_service)

        def failing_handler(s):
            raise RuntimeError("handler failed")

        dispatcher.register("fail_test", failing_handler)
        signal_service.emit("fail_test", {})

        count = dispatcher.dispatch_once()
        assert count == 0

        # Signal should still be unprocessed
        unprocessed = signal_service.get_unprocessed("fail_test")
        assert len(unprocessed) == 1

    def test_dispatch_unregistered_signal_marks_processed(self, signal_service):
        dispatcher = Dispatcher(signal_service)
        signal_service.emit("unknown_type", {})

        count = dispatcher.dispatch_once()
        assert count == 1

        unprocessed = signal_service.get_unprocessed("unknown_type")
        assert len(unprocessed) == 0

    def test_dispatch_idempotent(self, signal_service):
        dispatcher = Dispatcher(signal_service)
        count_list = []
        dispatcher.register("idem", lambda s: count_list.append(1))

        signal_service.emit("idem", {})
        dispatcher.dispatch_once()
        dispatcher.dispatch_once()

        assert len(count_list) == 1

    def test_dispatch_partial_handler_failure(self, signal_service):
        """When handler B throws after handler A succeeds, the signal stays
        unprocessed.  Next poll re-runs handler A, causing duplicate side effects.

        This test documents the known limitation so future refactors can address it.
        """
        dispatcher = Dispatcher(signal_service)
        side_effects: list[str] = []

        dispatcher.register("partial", lambda s: side_effects.append("A"))
        dispatcher.register("partial", lambda s: (_ for _ in ()).throw(RuntimeError("B failed")))

        signal_service.emit("partial", {})

        # First dispatch: A runs, then B raises -- signal NOT marked processed
        count = dispatcher.dispatch_once()
        assert count == 0
        assert side_effects == ["A"]

        # Second dispatch: signal still unprocessed, so A runs *again*
        count = dispatcher.dispatch_once()
        assert count == 0
        assert side_effects == ["A", "A"]  # duplicate side effect from A
