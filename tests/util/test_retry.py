import pytest
from mailagent.util.retry import retry


def test_retry_returns_on_first_success():
    calls = []
    result = retry(lambda: calls.append(1) or "ok", sleep=lambda s: None)
    assert result == "ok"
    assert len(calls) == 1


def test_retry_succeeds_after_transient_failures():
    state = {"n": 0}
    delays = []

    def flaky():
        state["n"] += 1
        if state["n"] < 3:
            raise RuntimeError("boom")
        return "done"

    result = retry(flaky, attempts=3, base_delay=1.0, sleep=delays.append)
    assert result == "done"
    assert state["n"] == 3
    assert delays == [1.0, 2.0]  # exponential: 1*2^0, 1*2^1


def test_retry_raises_after_exhausting_attempts():
    delays = []

    def always_fails():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        retry(always_fails, attempts=3, base_delay=1.0, sleep=delays.append)
    assert delays == [1.0, 2.0]  # slept between the 3 attempts, not after the last
