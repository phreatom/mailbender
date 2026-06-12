from datetime import datetime, timedelta
from mailbender.scheduler.loop import _due, run_loop


def test_due_logic():
    now = datetime(2026, 6, 12, 12, 0, 0)
    assert _due(None, now, 15) is True            # never run -> due
    assert _due(now - timedelta(minutes=20), now, 15) is True   # interval elapsed
    assert _due(now - timedelta(minutes=5), now, 15) is False   # too soon
    assert _due(None, now, 0) is False            # 0 = manual-only, never auto


class FakeRepo:
    def __init__(self, last):
        self._last = last

    def last_run_at(self, run_type):
        return self._last.get(run_type)


class FakeRunner:
    def __init__(self, last):
        self.repo = FakeRepo(last)
        self.dispatched = []

    def run_main(self):
        self.dispatched.append("main")

    def run_feedback(self):
        self.dispatched.append("feedback")

    def run_style(self):
        self.dispatched.append("style")


def test_run_loop_dispatches_due_run_types():
    now = datetime(2026, 6, 12, 12, 0, 0)
    runner = FakeRunner(last={
        "main": now - timedelta(minutes=20),     # due (interval 15)
        "feedback": now - timedelta(minutes=5),  # not due (interval 60)
    })
    run_loop(
        build_runner_fn=lambda: runner,
        intervals={"main": 15, "feedback": 60, "style": 0},
        clock=lambda: now,
        sleep=lambda s: None,
        max_cycles=1,
    )
    assert runner.dispatched == ["main"]  # feedback too soon, style manual-only


def test_run_loop_first_run_fires_all_enabled():
    now = datetime(2026, 6, 12, 12, 0, 0)
    runner = FakeRunner(last={})  # nothing ever ran
    run_loop(
        build_runner_fn=lambda: runner,
        intervals={"main": 15, "feedback": 60, "style": 0},
        clock=lambda: now,
        sleep=lambda s: None,
        max_cycles=1,
    )
    assert runner.dispatched == ["main", "feedback"]  # style disabled (0)


def test_run_loop_survives_dispatch_failure():
    now = datetime(2026, 6, 12, 12, 0, 0)

    class ExplodingRunner:
        def __init__(self):
            self.repo = FakeRepo(last={})
            self.dispatched = []

        def run_main(self):
            raise RuntimeError("imap down")

        def run_feedback(self):
            self.dispatched.append("feedback")

        def run_style(self):
            self.dispatched.append("style")

    runner = ExplodingRunner()
    # Should not raise even though run_main blows up; feedback still fires.
    run_loop(
        build_runner_fn=lambda: runner,
        intervals={"main": 15, "feedback": 60, "style": 0},
        clock=lambda: now,
        sleep=lambda s: None,
        max_cycles=1,
    )
    assert runner.dispatched == ["feedback"]
