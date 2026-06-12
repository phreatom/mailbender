import time
from datetime import datetime

_DISPATCH = {
    "main": lambda r: r.run_main(),
    "feedback": lambda r: r.run_feedback(),
    "style": lambda r: r.run_style(),
}


def _due(last, now, minutes: int) -> bool:
    """True if a run type with the given interval should fire now."""
    if minutes <= 0:
        return False  # 0 (or negative) means manual-only
    if last is None:
        return True
    return (now - last).total_seconds() >= minutes * 60


def run_loop(build_runner_fn, intervals, *, clock=datetime.utcnow,
             sleep=time.sleep, tick_seconds: int = 60, max_cycles=None):
    """Periodically fire due run types.

    A fresh runner is built each cycle (fresh DB session). For each run type
    in `intervals`, fire it if its interval has elapsed since the last
    `run_history` marker. `clock`/`sleep`/`max_cycles` are injectable so tests
    run deterministically without real time.
    """
    cycles = 0
    while max_cycles is None or cycles < max_cycles:
        runner = build_runner_fn()
        now = clock()
        for run_type, minutes in intervals.items():
            if _due(runner.repo.last_run_at(run_type), now, minutes):
                try:
                    _DISPATCH[run_type](runner)
                except Exception:
                    # A run-level failure (e.g. IMAP down after retries) must
                    # never kill the loop. No success marker is written, so the
                    # next cycle simply retries this run type.
                    continue
        cycles += 1
        if max_cycles is None or cycles < max_cycles:
            sleep(tick_seconds)
