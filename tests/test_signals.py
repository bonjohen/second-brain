"""Tests for SignalService."""


class TestSignalService:
    def test_emit_creates_signal(self, signal_service):
        signal = signal_service.emit("new_note", {"note_id": "abc"})
        assert signal.type == "new_note"
        assert signal.payload == {"note_id": "abc"}
        assert signal.processed_at is None

    def test_get_unprocessed_returns_unprocessed(self, signal_service):
        signal_service.emit("new_note", {"id": "1"})
        signal_service.emit("new_note", {"id": "2"})

        unprocessed = signal_service.get_unprocessed()
        assert len(unprocessed) == 2

    def test_get_unprocessed_filters_by_type(self, signal_service):
        signal_service.emit("new_note", {"id": "1"})
        signal_service.emit("belief_proposed", {"id": "2"})

        unprocessed = signal_service.get_unprocessed("new_note")
        assert len(unprocessed) == 1
        assert unprocessed[0].type == "new_note"

    def test_mark_processed(self, signal_service):
        signal = signal_service.emit("new_note")
        signal_service.mark_processed(signal.signal_id)

        unprocessed = signal_service.get_unprocessed()
        assert len(unprocessed) == 0

    def test_processed_signal_not_in_unprocessed(self, signal_service):
        s1 = signal_service.emit("new_note", {"id": "1"})
        signal_service.emit("new_note", {"id": "2"})

        signal_service.mark_processed(s1.signal_id)

        unprocessed = signal_service.get_unprocessed()
        assert len(unprocessed) == 1
        assert unprocessed[0].payload == {"id": "2"}

    def test_get_unprocessed_respects_limit(self, signal_service):
        for i in range(5):
            signal_service.emit("batch", {"id": str(i)})

        limited = signal_service.get_unprocessed(limit=3)
        assert len(limited) == 3

    def test_get_unprocessed_with_type_respects_limit(self, signal_service):
        for i in range(5):
            signal_service.emit("typed", {"id": str(i)})

        limited = signal_service.get_unprocessed("typed", limit=2)
        assert len(limited) == 2
