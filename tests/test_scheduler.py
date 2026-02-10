"""Tests for the scheduler."""

from second_brain.runtime.scheduler import Scheduler


class TestScheduler:
    def test_tick_no_steps(self):
        scheduler = Scheduler()
        results = scheduler.tick()
        assert results == []

    def test_tick_runs_steps_in_order(self):
        scheduler = Scheduler()
        order = []
        scheduler.register("first", lambda: order.append("first"))
        scheduler.register("second", lambda: order.append("second"))
        scheduler.register("third", lambda: order.append("third"))

        scheduler.tick()
        assert order == ["first", "second", "third"]

    def test_tick_returns_results(self):
        scheduler = Scheduler()
        scheduler.register("step_a", lambda: 42)
        scheduler.register("step_b", lambda: "done")

        results = scheduler.tick()
        assert results == [("step_a", 42), ("step_b", "done")]

    def test_tick_handles_step_failure(self):
        scheduler = Scheduler()
        scheduler.register("ok", lambda: "ok")
        scheduler.register("fail", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        scheduler.register("after", lambda: "after")

        results = scheduler.tick()
        assert results[0] == ("ok", "ok")
        assert results[1] == ("fail", None)
        assert results[2] == ("after", "after")

    def test_run_once(self):
        scheduler = Scheduler()
        scheduler.register("step", lambda: "result")
        results = scheduler.run_once()
        assert len(results) == 1
        assert results[0] == ("step", "result")

    def test_run_continuous_max_ticks(self):
        # Termination is controlled by max_ticks (not wall-clock timing).
        # The small tick_interval only affects the sleep between ticks;
        # the test is deterministic because it exits after exactly 3 ticks.
        scheduler = Scheduler(tick_interval=0.01)
        counter = {"n": 0}

        def increment():
            counter["n"] += 1

        scheduler.register("count", increment)
        scheduler.run_continuous(max_ticks=3)

        assert counter["n"] == 3

    def test_stop(self):
        # stop() sets a threading.Event, so the scheduler exits immediately
        # after the step calls stop(). No timing dependency — deterministic.
        scheduler = Scheduler(tick_interval=0.01)
        counter = {"n": 0}

        def increment_and_stop():
            counter["n"] += 1
            if counter["n"] >= 2:
                scheduler.stop()

        scheduler.register("stopper", increment_and_stop)
        scheduler.run_continuous()

        assert counter["n"] == 2

    def test_failure_counter_increments(self):
        scheduler = Scheduler()
        scheduler.register("flaky", lambda: (_ for _ in ()).throw(RuntimeError("oops")))

        scheduler.tick()
        assert scheduler.failure_counts["flaky"] == 1

        scheduler.tick()
        assert scheduler.failure_counts["flaky"] == 2
