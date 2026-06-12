# Milestone 2 — Feature-Complete v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn mailagent into a self-running service and expose every core capability through CLI and API, completing the design spec (`docs/superpowers/specs/2026-06-12-milestone-2-feature-complete-v1-design.md`).

**Architecture:** Build on the existing modular monolith. Add a testable scheduler loop (injected clock/sleep), run-history recording in the `Runner`, a small retry/backoff utility wired into the IMAP client and OpenAI provider, and full CLI + API surfaces following the established `Repository` / `Runner` / `build_runner` / `create_app` / `cli/main.py` patterns. Add a scheduler container and `alembic upgrade head` bootstrap to deployment.

**Tech Stack:** Python 3.12, FastAPI, Typer, SQLAlchemy 2.x, Alembic, psycopg, pgvector, IMAPClient, pytest, pytest-docker (Greenmail + Postgres).

---

## File Structure

```
src/mailagent/
  config.py                  # MODIFY: add feedback_minutes, style_minutes
  util/
    __init__.py              # CREATE (empty)
    retry.py                 # CREATE: retry(fn, attempts, base_delay, sleep)
  llm/openai_provider.py     # MODIFY: wrap network calls in retry
  imap/client.py             # MODIFY: wrap _connect in retry
  store/repository.py        # MODIFY: run-history + query + mapping helpers
  scheduler/
    runner.py                # MODIFY: write run_history rows
    loop.py                  # CREATE: _due() + run_loop()
  api/
    app.py                   # MODIFY: new endpoints + runner/chat factories
    routes.py                # MODIFY: response-shaping helpers
  cli/main.py                # MODIFY: chat/history/audit/priorities/mappings/scheduler/run-style/run-feedback
tests/
  util/test_retry.py         # CREATE
  llm/test_openai_provider.py# MODIFY: add retry test
  imap/test_client.py        # MODIFY: add connect-retry unit test
  store/test_repository.py   # MODIFY: run-history + query + mapping tests
  scheduler/test_runner.py   # MODIFY: run-history assertions
  scheduler/test_loop.py     # CREATE
  cli/test_main.py           # MODIFY: new command tests
  api/test_app.py            # MODIFY: new endpoint tests
Dockerfile                   # MODIFY: entrypoint runs alembic upgrade head
docker-entrypoint.sh         # CREATE
docker-compose.yml           # MODIFY: add scheduler service
migrations/env.py            # MODIFY: prefer MAILAGENT_DATABASE_URL
.env.example                 # MODIFY: feedback/style minutes
```

Tests use the existing fixtures: `db_session` (savepoint-isolated, `tests/conftest.py`), `db_engine`, `FakeLLMProvider`, Greenmail `imap`. New deterministic seams are injected `clock`/`sleep` and fake factories.

---

## Task 1: Config — per-type schedule intervals

**Files:**
- Modify: `src/mailagent/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:
```python
def test_schedule_interval_defaults(monkeypatch):
    monkeypatch.setenv("MAILAGENT_DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("MAILAGENT_IMAP_HOST", "h")
    monkeypatch.setenv("MAILAGENT_IMAP_USER", "u")
    monkeypatch.setenv("MAILAGENT_IMAP_PASSWORD", "p")
    from mailagent.config import load_config
    cfg = load_config()
    assert cfg.schedule_minutes == 15
    assert cfg.feedback_minutes == 60
    assert cfg.style_minutes == 0  # 0 = manual-only


def test_schedule_intervals_from_env(monkeypatch):
    monkeypatch.setenv("MAILAGENT_DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("MAILAGENT_IMAP_HOST", "h")
    monkeypatch.setenv("MAILAGENT_IMAP_USER", "u")
    monkeypatch.setenv("MAILAGENT_IMAP_PASSWORD", "p")
    monkeypatch.setenv("MAILAGENT_FEEDBACK_MINUTES", "30")
    monkeypatch.setenv("MAILAGENT_STYLE_MINUTES", "1440")
    from mailagent.config import load_config
    cfg = load_config()
    assert cfg.feedback_minutes == 30
    assert cfg.style_minutes == 1440
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError: 'Config' object has no attribute 'feedback_minutes'`

- [ ] **Step 3: Write the implementation**

In `src/mailagent/config.py`, add two fields to `Config` (after `schedule_minutes`):
```python
    schedule_minutes: int = 15
    feedback_minutes: int = 60
    style_minutes: int = 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/config.py tests/test_config.py
git commit -m "feat: add feedback/style schedule intervals to config"
```

---

## Task 2: Retry utility with exponential backoff

**Files:**
- Create: `src/mailagent/util/__init__.py`
- Create: `src/mailagent/util/retry.py`
- Create: `tests/util/__init__.py`
- Test: `tests/util/test_retry.py`

- [ ] **Step 1: Write the failing test**

`tests/util/__init__.py`: (empty file)

`tests/util/test_retry.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/util/test_retry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.util'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/util/__init__.py`: (empty file)

`src/mailagent/util/retry.py`:
```python
import time


def retry(fn, *, attempts: int = 3, base_delay: float = 1.0,
          sleep=time.sleep, exceptions: tuple = (Exception,)):
    """Call fn(); on a listed exception, retry with exponential backoff.

    Sleeps base_delay * 2**(n-1) between attempts (never after the last).
    `sleep` is injectable so tests run without real delays. Re-raises the
    last exception once attempts are exhausted.
    """
    for n in range(1, attempts + 1):
        try:
            return fn()
        except exceptions:
            if n == attempts:
                raise
            sleep(base_delay * (2 ** (n - 1)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/util/test_retry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/util tests/util
git commit -m "feat: add retry utility with exponential backoff"
```

---

## Task 3: Wrap OpenAI provider calls in retry

**Files:**
- Modify: `src/mailagent/llm/openai_provider.py`
- Test: `tests/llm/test_openai_provider.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/llm/test_openai_provider.py`:
```python
def test_chat_retries_transient_failure(monkeypatch):
    import mailagent.llm.openai_provider as mod
    from mailagent.llm.provider import Email

    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    state = {"n": 0}

    class FlakyClient:
        def __init__(self):
            outer = self

            class Chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        state["n"] += 1
                        if state["n"] < 2:
                            raise RuntimeError("transient")
                        return type("R", (), {"choices": [
                            type("C", (), {"message": type("M", (), {"content": "Newsletter"})})
                        ]})

            self.chat = Chat()

    provider = mod.OpenAIProvider(client=FlakyClient())
    email = Email(uid="1", subject="s", sender="a@b.c", body="b")
    assert provider.classify(email, ["Newsletter"]) == "Newsletter"
    assert state["n"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/llm/test_openai_provider.py::test_chat_retries_transient_failure -v`
Expected: FAIL with `AttributeError: module 'mailagent.llm.openai_provider' has no attribute 'time'` (or a RuntimeError, since calls are not yet retried)

- [ ] **Step 3: Write the implementation**

In `src/mailagent/llm/openai_provider.py`, add imports at the top (below the existing `from mailagent.llm.provider import Email`):
```python
import time
from mailagent.util.retry import retry
```

Replace the `_chat` and `embed` methods with retry-wrapped versions:
```python
    def _chat(self, prompt: str) -> str:
        def call():
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.choices[0].message.content.strip()
        return retry(call, sleep=time.sleep)

    def embed(self, text: str) -> list[float]:
        def call():
            resp = self.client.embeddings.create(
                model=self.embed_model, input=text)
            return list(resp.data[0].embedding)
        return retry(call, sleep=time.sleep)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/llm/test_openai_provider.py -v`
Expected: PASS (existing happy-path tests still pass; retry only kicks in on failure)

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/llm/openai_provider.py tests/llm/test_openai_provider.py
git commit -m "feat: retry openai provider network calls with backoff"
```

---

## Task 4: Wrap IMAP connect in retry

**Files:**
- Modify: `src/mailagent/imap/client.py`
- Test: `tests/imap/test_client.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/imap/test_client.py` (this is a pure unit test — it does not need the Greenmail container):
```python
def test_connect_retries_transient_failure(monkeypatch):
    import mailagent.imap.client as mod

    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    state = {"n": 0}

    class FakeIMAP:
        def __init__(self, host, port=0, ssl=False):
            state["n"] += 1
            if state["n"] < 2:
                raise OSError("connection refused")

        def login(self, user, password):
            return "ok"

    monkeypatch.setattr(mod, "IMAPClient", FakeIMAP)
    client = mod.ImapClient(host="h", port=1, user="u", password="p", use_ssl=False)
    conn = client._connect()
    assert isinstance(conn, FakeIMAP)
    assert state["n"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/imap/test_client.py::test_connect_retries_transient_failure -v`
Expected: FAIL with `AttributeError: module 'mailagent.imap.client' has no attribute 'time'` (or OSError, since connect is not yet retried)

- [ ] **Step 3: Write the implementation**

In `src/mailagent/imap/client.py`, add imports at the top (alongside the existing imports):
```python
import time
from mailagent.util.retry import retry
```

Replace the `_connect` method with:
```python
    def _connect(self) -> IMAPClient:
        def do():
            client = IMAPClient(self.host, port=self.port, ssl=self.use_ssl)
            client.login(self.user, self.password)
            return client
        return retry(do, sleep=time.sleep)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/imap/test_client.py::test_connect_retries_transient_failure -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/imap/client.py tests/imap/test_client.py
git commit -m "feat: retry imap connect with backoff"
```

---

## Task 5: Repository — run-history helpers

**Files:**
- Modify: `src/mailagent/store/repository.py`
- Test: `tests/store/test_repository.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/store/test_repository.py`:
```python
def test_record_and_query_run_history(repo):
    repo.record_run_step("main", "uid-1", "classify", "success", "Newsletter")
    repo.record_run_step("main", None, "run", "success")
    runs = repo.recent_runs(limit=10)
    assert len(runs) == 2
    assert {r.step for r in runs} == {"classify", "run"}


def test_last_run_at_returns_none_then_timestamp(repo):
    assert repo.last_run_at("main") is None
    repo.record_run_step("main", None, "run", "success")
    assert repo.last_run_at("main") is not None
    assert repo.last_run_at("feedback") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_repository.py::test_record_and_query_run_history -v`
Expected: FAIL with `AttributeError: 'Repository' object has no attribute 'record_run_step'`

- [ ] **Step 3: Write the implementation**

In `src/mailagent/store/repository.py`, update the imports line and add the methods. Change:
```python
from mailagent.store.models import ProcessedMail, Category
```
to:
```python
from mailagent.store.models import (
    ProcessedMail, Category, RunHistory, AuditLog, FolderMapping,
)
from sqlalchemy import desc, case
```

Add these methods to the `Repository` class:
```python
    def record_run_step(self, run_type, uid, step, result, detail=""):
        self.session.add(RunHistory(
            run_type=run_type, uid=uid, step=step,
            result=result, detail=detail,
        ))
        self.session.commit()

    def last_run_at(self, run_type):
        stmt = (select(func.max(RunHistory.created_at))
                .where(RunHistory.run_type == run_type)
                .where(RunHistory.step == "run"))
        return self.session.execute(stmt).scalar_one_or_none()

    def recent_runs(self, limit: int = 50):
        stmt = (select(RunHistory)
                .order_by(desc(RunHistory.created_at))
                .limit(limit))
        return self.session.execute(stmt).scalars().all()
```

(`AuditLog`, `FolderMapping`, and `case` are imported now but used in Tasks 8–9.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/store/test_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/store/repository.py tests/store/test_repository.py
git commit -m "feat: add run-history repository helpers"
```

---

## Task 6: Runner records run-history

**Files:**
- Modify: `src/mailagent/scheduler/runner.py`
- Test: `tests/scheduler/test_runner.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/scheduler/test_runner.py`:
```python
def test_main_run_records_history_steps(session):
    from sqlalchemy import select
    from mailagent.store.models import RunHistory
    inbox = [Email(uid="1", subject="Frage", sender="a@b.c", body="?",
                   message_id="<m1>")]
    imap = FakeImap(inbox)
    provider = FakeLLMProvider(category="Antwort nötig", priority="high",
                               draft="Hallo!")
    runner = Runner(
        imap=imap, provider=provider, session=session,
        categories=["Antwort nötig"], mapping={},
        reply_category="Antwort nötig", style_examples=["Grüße"],
    )
    runner.run_main()
    rows = session.execute(select(RunHistory)).scalars().all()
    steps = {r.step for r in rows}
    assert {"classify", "prioritize", "index", "move", "draft", "run"} <= steps
    marker = [r for r in rows if r.step == "run"]
    assert len(marker) == 1 and marker[0].run_type == "main"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scheduler/test_runner.py::test_main_run_records_history_steps -v`
Expected: FAIL — no `RunHistory` rows are written yet (assertion error on `steps`).

- [ ] **Step 3: Write the implementation**

In `src/mailagent/scheduler/runner.py`, replace the `run_main`, `run_style`, and `run_feedback` methods with:
```python
    def run_main(self):
        for email in self.imap.fetch_inbox():
            if self.repo.is_processed(email.uid):
                continue
            try:
                category = self.classifier.classify(email, self.categories)
                self.repo.record_run_step("main", email.uid, "classify",
                                          "success", category)
                priority = self.prioritizer.prioritize(email)
                self.repo.record_run_step("main", email.uid, "prioritize",
                                          "success", priority)
                self.indexer.index(email)
                self.repo.record_run_step("main", email.uid, "index", "success")
                moved = self.mover.maybe_move(email.uid, category)
                self.repo.record_run_step("main", email.uid, "move",
                                          "success" if moved else "skipped")
                drafted = False
                if category == self.reply_category:
                    self.draft_generator.generate(email, self.style_examples)
                    self.audit.record("scheduler", "draft_append", email.uid)
                    self.repo.record_run_step("main", email.uid, "draft", "success")
                    drafted = True
                else:
                    self.repo.record_run_step("main", email.uid, "draft", "skipped")
                self.repo.mark_processed(
                    email.uid, category, priority, moved, drafted)
            except Exception:  # per-mail isolation
                self.audit.record("scheduler", "process_error",
                                  email.uid, result="error")
                self.repo.record_run_step("main", email.uid, "process", "error")
                continue
        self.repo.record_run_step("main", None, "run", "success")

    def run_style(self):
        StyleLearner(self.imap, self.session).bootstrap()
        self.repo.record_run_step("style", None, "run", "success")

    def run_feedback(self):
        FeedbackLearner(self.imap, self.session).run()
        self.repo.record_run_step("feedback", None, "run", "success")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/scheduler/test_runner.py tests/scheduler/test_runner_extra.py -v`
Expected: PASS (existing runner tests still green)

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/scheduler/runner.py tests/scheduler/test_runner.py
git commit -m "feat: record per-step and per-pass run history in runner"
```

---

## Task 7: Scheduler loop with per-type cadence

**Files:**
- Create: `src/mailagent/scheduler/loop.py`
- Create: `tests/scheduler/test_loop.py`

- [ ] **Step 1: Write the failing test**

`tests/scheduler/test_loop.py`:
```python
from datetime import datetime, timedelta
from mailagent.scheduler.loop import _due, run_loop


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scheduler/test_loop.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.scheduler.loop'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/scheduler/loop.py`:
```python
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
                _DISPATCH[run_type](runner)
        cycles += 1
        if max_cycles is None or cycles < max_cycles:
            sleep(tick_seconds)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/scheduler/test_loop.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/scheduler/loop.py tests/scheduler/test_loop.py
git commit -m "feat: add scheduler loop with per-type cadence"
```

---

## Task 8: Repository — audit + priority query helpers

**Files:**
- Modify: `src/mailagent/store/repository.py`
- Test: `tests/store/test_repository.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/store/test_repository.py`:
```python
def test_recent_audit_returns_entries(repo):
    from mailagent.audit.log import AuditLogger
    AuditLogger(repo.session).record("scheduler", "draft_append", "uid-1")
    rows = repo.recent_audit(limit=10)
    assert len(rows) == 1
    assert rows[0].action == "draft_append"


def test_processed_by_priority_orders_high_first(repo):
    repo.mark_processed("a", "X", "low", False, False)
    repo.mark_processed("b", "X", "high", False, False)
    repo.mark_processed("c", "X", "medium", False, False)
    order = [p.priority for p in repo.processed_by_priority()]
    assert order == ["high", "medium", "low"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_repository.py::test_processed_by_priority_orders_high_first -v`
Expected: FAIL with `AttributeError: 'Repository' object has no attribute 'processed_by_priority'`

- [ ] **Step 3: Write the implementation**

Add to the `Repository` class in `src/mailagent/store/repository.py` (imports for `AuditLog`, `case`, `desc` were added in Task 5):
```python
    def recent_audit(self, limit: int = 50):
        stmt = (select(AuditLog)
                .order_by(desc(AuditLog.created_at))
                .limit(limit))
        return self.session.execute(stmt).scalars().all()

    def processed_by_priority(self):
        order = case(
            (ProcessedMail.priority == "high", 0),
            (ProcessedMail.priority == "medium", 1),
            (ProcessedMail.priority == "low", 2),
            else_=3,
        )
        stmt = select(ProcessedMail).order_by(order, ProcessedMail.uid)
        return self.session.execute(stmt).scalars().all()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/store/test_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/store/repository.py tests/store/test_repository.py
git commit -m "feat: add audit and priority query helpers to repository"
```

---

## Task 9: Repository — folder-mapping CRUD

**Files:**
- Modify: `src/mailagent/store/repository.py`
- Test: `tests/store/test_repository.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/store/test_repository.py`:
```python
def test_add_list_remove_mapping(repo):
    repo.add_mapping("Newsletter", "Archive/News")
    mappings = {m.category_name: m.target_folder for m in repo.list_mappings()}
    assert mappings == {"Newsletter": "Archive/News"}
    assert repo.remove_mapping("Newsletter") is True
    assert repo.list_mappings() == []
    assert repo.remove_mapping("Newsletter") is False


def test_add_mapping_upserts_target(repo):
    repo.add_mapping("Newsletter", "Archive/News")
    repo.add_mapping("Newsletter", "Archive/Old")
    mappings = {m.category_name: m.target_folder for m in repo.list_mappings()}
    assert mappings == {"Newsletter": "Archive/Old"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_repository.py::test_add_list_remove_mapping -v`
Expected: FAIL with `AttributeError: 'Repository' object has no attribute 'add_mapping'`

- [ ] **Step 3: Write the implementation**

Add to the `Repository` class in `src/mailagent/store/repository.py` (`FolderMapping` was imported in Task 5):
```python
    def add_mapping(self, category_name: str, target_folder: str):
        stmt = insert(FolderMapping).values(
            category_name=category_name, target_folder=target_folder
        ).on_conflict_do_update(
            index_elements=["category_name"],
            set_={"target_folder": target_folder},
        )
        self.session.execute(stmt)
        self.session.commit()

    def list_mappings(self):
        return self.session.execute(select(FolderMapping)).scalars().all()

    def remove_mapping(self, category_name: str) -> bool:
        stmt = select(FolderMapping).where(
            FolderMapping.category_name == category_name)
        obj = self.session.execute(stmt).scalar_one_or_none()
        if obj is None:
            return False
        self.session.delete(obj)
        self.session.commit()
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/store/test_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/store/repository.py tests/store/test_repository.py
git commit -m "feat: add folder-mapping CRUD to repository"
```

---

## Task 10: CLI — scheduler, run-style, run-feedback

**Files:**
- Modify: `src/mailagent/cli/main.py`
- Test: `tests/cli/test_main.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/cli/test_main.py`:
```python
def test_scheduler_command_invokes_run_loop(monkeypatch):
    from mailagent.cli import main

    captured = {}

    def fake_run_loop(build_runner_fn, intervals, **kwargs):
        captured["intervals"] = intervals

    class FakeCfg:
        schedule_minutes = 15
        feedback_minutes = 60
        style_minutes = 0

    monkeypatch.setattr(main, "_load_config", lambda: FakeCfg())
    monkeypatch.setattr(main, "run_loop", fake_run_loop)
    monkeypatch.setattr(main, "_make_runner", lambda: object())
    result = runner.invoke(app, ["scheduler"])
    assert result.exit_code == 0
    assert captured["intervals"] == {"main": 15, "feedback": 60, "style": 0}


def test_run_style_command(monkeypatch):
    from mailagent.cli import main

    class FakeRunner:
        def __init__(self):
            self.called = False

        def run_style(self):
            self.called = True

    fake = FakeRunner()
    monkeypatch.setattr(main, "_make_runner", lambda: fake)
    result = runner.invoke(app, ["run-style"])
    assert result.exit_code == 0
    assert fake.called is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cli/test_main.py::test_run_style_command -v`
Expected: FAIL with `SystemExit: 2` / "No such command 'run-style'" (commands not defined yet)

- [ ] **Step 3: Write the implementation**

In `src/mailagent/cli/main.py`, add a module-level import near the top (below `from mailagent import __version__`):
```python
from mailagent.scheduler.loop import run_loop
```

Add a config helper (near the other `_make_*` helpers):
```python
def _load_config():
    from mailagent.config import load_config
    return load_config()
```

Add the three commands (before `if __name__ == "__main__":`):
```python
@app.command()
def scheduler():
    """Run the periodic scheduler loop (foreground; for the scheduler container)."""
    cfg = _load_config()
    intervals = {
        "main": cfg.schedule_minutes,
        "feedback": cfg.feedback_minutes,
        "style": cfg.style_minutes,
    }
    typer.echo("Starting scheduler loop...")
    run_loop(_make_runner, intervals)


@app.command("run-style")
def run_style():
    """Bootstrap the writing-style profile from the Sent folder now."""
    _make_runner().run_style()
    typer.echo("Style run complete.")


@app.command("run-feedback")
def run_feedback():
    """Run the draft-vs-sent feedback pass now."""
    _make_runner().run_feedback()
    typer.echo("Feedback run complete.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/cli/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/cli/main.py tests/cli/test_main.py
git commit -m "feat: add cli scheduler, run-style, run-feedback commands"
```

---

## Task 11: CLI — chat

**Files:**
- Modify: `src/mailagent/cli/main.py`
- Test: `tests/cli/test_main.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/cli/test_main.py`:
```python
def test_chat_command(monkeypatch):
    from mailagent.cli import main
    from mailagent.chat.chat import ChatAnswer, ChatSource

    class FakeChat:
        def ask(self, question):
            return ChatAnswer(text="Sarah approved it.",
                              sources=[ChatSource(uid="1", subject="Budget")])

    monkeypatch.setattr(main, "_make_chat", lambda: FakeChat())
    result = runner.invoke(app, ["chat", "What did Sarah say?"])
    assert result.exit_code == 0
    assert "Sarah approved it." in result.stdout
    assert "1" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cli/test_main.py::test_chat_command -v`
Expected: FAIL with "No such command 'chat'"

- [ ] **Step 3: Write the implementation**

In `src/mailagent/cli/main.py`, add a `_make_chat` helper (near the other `_make_*` helpers):
```python
def _make_chat():
    from mailagent.config import load_config
    from mailagent.llm.factory import make_provider
    from mailagent.chat.chat import Chat
    cfg = load_config()
    session = _make_session(cfg)
    api_key = cfg.llm_api_key.get_secret_value() if cfg.llm_api_key else None
    provider = make_provider(cfg.llm_provider, api_key)
    return Chat(provider, session)
```

Add the command:
```python
@app.command()
def chat(question: str):
    """Ask a question about the mailbox."""
    answer = _make_chat().ask(question)
    typer.echo(answer.text)
    if answer.sources:
        typer.echo("Quellen:")
        for s in answer.sources:
            typer.echo(f"  [{s.uid}] {s.subject}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/cli/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/cli/main.py tests/cli/test_main.py
git commit -m "feat: add cli chat command"
```

---

## Task 12: CLI — history and audit

**Files:**
- Modify: `src/mailagent/cli/main.py`
- Test: `tests/cli/test_main.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/cli/test_main.py`:
```python
def test_history_command(monkeypatch):
    from mailagent.cli import main

    class Row:
        run_type = "main"; uid = "1"; step = "classify"
        result = "success"; detail = "Newsletter"

    class FakeRepo:
        def recent_runs(self, limit=50):
            return [Row()]

    monkeypatch.setattr(main, "_make_repo", lambda: FakeRepo())
    result = runner.invoke(app, ["history"])
    assert result.exit_code == 0
    assert "classify" in result.stdout


def test_audit_command(monkeypatch):
    from mailagent.cli import main

    class Row:
        actor = "scheduler"; action = "draft_append"
        target = "uid-1"; result = "success"

    class FakeRepo:
        def recent_audit(self, limit=50):
            return [Row()]

    monkeypatch.setattr(main, "_make_repo", lambda: FakeRepo())
    result = runner.invoke(app, ["audit"])
    assert result.exit_code == 0
    assert "draft_append" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cli/test_main.py::test_history_command -v`
Expected: FAIL with "No such command 'history'"

- [ ] **Step 3: Write the implementation**

Add to `src/mailagent/cli/main.py`:
```python
@app.command()
def history(limit: int = 50):
    """Show recent run history."""
    repo = _make_repo()
    for r in repo.recent_runs(limit):
        typer.echo(f"{r.run_type:8} {str(r.uid):8} {r.step:10} "
                   f"{r.result:8} {r.detail}")


@app.command()
def audit(limit: int = 50):
    """Show recent audit-log entries."""
    repo = _make_repo()
    for r in repo.recent_audit(limit):
        typer.echo(f"{r.actor:10} {r.action:16} {r.target:12} {r.result}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/cli/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/cli/main.py tests/cli/test_main.py
git commit -m "feat: add cli history and audit commands"
```

---

## Task 13: CLI — priorities

**Files:**
- Modify: `src/mailagent/cli/main.py`
- Test: `tests/cli/test_main.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/cli/test_main.py`:
```python
def test_priorities_command(monkeypatch):
    from mailagent.cli import main

    class Row:
        def __init__(self, uid, priority, category):
            self.uid = uid; self.priority = priority; self.category = category

    class FakeRepo:
        def processed_by_priority(self):
            return [Row("1", "high", "Antwort nötig"),
                    Row("2", "low", "Newsletter")]

    monkeypatch.setattr(main, "_make_repo", lambda: FakeRepo())
    result = runner.invoke(app, ["priorities"])
    assert result.exit_code == 0
    assert "high" in result.stdout
    assert result.stdout.index("high") < result.stdout.index("low")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cli/test_main.py::test_priorities_command -v`
Expected: FAIL with "No such command 'priorities'"

- [ ] **Step 3: Write the implementation**

Add to `src/mailagent/cli/main.py`:
```python
@app.command()
def priorities():
    """List processed mail sorted by priority (high first)."""
    repo = _make_repo()
    marks = {"high": "!!!", "medium": "!", "low": " "}
    for p in repo.processed_by_priority():
        typer.echo(f"{marks.get(p.priority, ' '):3} {p.priority:7} "
                   f"[{p.uid}] {p.category}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/cli/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/cli/main.py tests/cli/test_main.py
git commit -m "feat: add cli priorities command"
```

---

## Task 14: CLI — folder-mapping commands

**Files:**
- Modify: `src/mailagent/cli/main.py`
- Test: `tests/cli/test_main.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/cli/test_main.py`:
```python
def test_mapping_commands(monkeypatch):
    from mailagent.cli import main

    store = {}

    class M:
        def __init__(self, c, f):
            self.category_name = c; self.target_folder = f

    class FakeRepo:
        def add_mapping(self, category, folder):
            store[category] = folder

        def list_mappings(self):
            return [M(c, f) for c, f in store.items()]

        def remove_mapping(self, category):
            return store.pop(category, None) is not None

    monkeypatch.setattr(main, "_make_repo", lambda: FakeRepo())
    assert runner.invoke(app, ["add-mapping", "Newsletter", "Archive/News"]).exit_code == 0
    out = runner.invoke(app, ["mappings"])
    assert "Newsletter" in out.stdout and "Archive/News" in out.stdout
    assert runner.invoke(app, ["remove-mapping", "Newsletter"]).exit_code == 0
    assert runner.invoke(app, ["remove-mapping", "Newsletter"]).exit_code == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cli/test_main.py::test_mapping_commands -v`
Expected: FAIL with "No such command 'add-mapping'"

- [ ] **Step 3: Write the implementation**

Add to `src/mailagent/cli/main.py`:
```python
@app.command("add-mapping")
def add_mapping(category: str, folder: str):
    """Map a category to a target IMAP folder (upserts)."""
    _make_repo().add_mapping(category, folder)
    typer.echo(f"Mapped {category} -> {folder}")


@app.command()
def mappings():
    """List category-to-folder mappings."""
    for m in _make_repo().list_mappings():
        typer.echo(f"{m.category_name} -> {m.target_folder}")


@app.command("remove-mapping")
def remove_mapping(category: str):
    """Remove a category-to-folder mapping."""
    if _make_repo().remove_mapping(category):
        typer.echo(f"Removed mapping: {category}")
    else:
        typer.echo(f"No such mapping: {category}")
        raise typer.Exit(code=1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/cli/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/cli/main.py tests/cli/test_main.py
git commit -m "feat: add cli folder-mapping commands"
```

---

## Task 15: API route helpers

**Files:**
- Modify: `src/mailagent/api/routes.py`
- Test: `tests/api/test_routes.py` (create)

- [ ] **Step 1: Write the failing test**

`tests/api/test_routes.py`:
```python
from mailagent.api import routes
from mailagent.chat.chat import ChatAnswer, ChatSource


class FakeChat:
    def ask(self, question):
        return ChatAnswer(text="answer",
                          sources=[ChatSource(uid="1", subject="s")])


def test_chat_answer_shape():
    out = routes.chat_answer(FakeChat(), "q")
    assert out == {"text": "answer", "sources": [{"uid": "1", "subject": "s"}]}


def test_priorities_shape():
    class P:
        uid = "1"; priority = "high"; category = "X"

    class Repo:
        def processed_by_priority(self):
            return [P()]

    assert routes.priorities(Repo()) == [
        {"uid": "1", "priority": "high", "category": "X"}]


def test_mappings_shape_and_mutations():
    store = {}

    class M:
        def __init__(self, c, f):
            self.category_name = c; self.target_folder = f

    class Repo:
        def list_mappings(self):
            return [M(c, f) for c, f in store.items()]

        def add_mapping(self, c, f):
            store[c] = f

        def remove_mapping(self, c):
            return store.pop(c, None) is not None

    assert routes.list_mappings(Repo()) == []
    assert routes.add_mapping(Repo(), "N", "F") == {"category": "N", "folder": "F"}
    assert routes.list_mappings(Repo()) == [{"category": "N", "folder": "F"}]
    assert routes.remove_mapping(Repo(), "N") == {"removed": True}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_routes.py -v`
Expected: FAIL with `AttributeError: module 'mailagent.api.routes' has no attribute 'chat_answer'`

- [ ] **Step 3: Write the implementation**

Replace `src/mailagent/api/routes.py` with:
```python
def list_categories(repo) -> list[str]:
    return [c.name for c in repo.list_categories()]


def chat_answer(chat, question: str) -> dict:
    ans = chat.ask(question)
    return {
        "text": ans.text,
        "sources": [{"uid": s.uid, "subject": s.subject} for s in ans.sources],
    }


def run_main(runner) -> dict:
    runner.run_main()
    return {"status": "ok"}


def recent_history(repo, limit: int) -> list[dict]:
    return [
        {"run_type": r.run_type, "uid": r.uid, "step": r.step,
         "result": r.result, "detail": r.detail}
        for r in repo.recent_runs(limit)
    ]


def recent_audit(repo, limit: int) -> list[dict]:
    return [
        {"actor": r.actor, "action": r.action, "target": r.target,
         "result": r.result}
        for r in repo.recent_audit(limit)
    ]


def priorities(repo) -> list[dict]:
    return [
        {"uid": p.uid, "priority": p.priority, "category": p.category}
        for p in repo.processed_by_priority()
    ]


def list_mappings(repo) -> list[dict]:
    return [
        {"category": m.category_name, "folder": m.target_folder}
        for m in repo.list_mappings()
    ]


def add_mapping(repo, category: str, folder: str) -> dict:
    repo.add_mapping(category, folder)
    return {"category": category, "folder": folder}


def remove_mapping(repo, category: str) -> dict:
    return {"removed": repo.remove_mapping(category)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/api/routes.py tests/api/test_routes.py
git commit -m "feat: add api response-shaping route helpers"
```

---

## Task 16: API — chat and run endpoints

**Files:**
- Modify: `src/mailagent/api/app.py`
- Test: `tests/api/test_app.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/api/test_app.py`:
```python
def test_chat_endpoint(monkeypatch):
    from mailagent.chat.chat import ChatAnswer, ChatSource
    app = create_app(api_token="t")

    class FakeChat:
        def ask(self, question):
            return ChatAnswer(text="A", sources=[ChatSource(uid="1", subject="s")])

    app.state.chat_factory = lambda: FakeChat()
    client = TestClient(app)
    resp = client.post("/chat", json={"question": "q"},
                       headers={"Authorization": "Bearer t"})
    assert resp.status_code == 200
    assert resp.json() == {"text": "A", "sources": [{"uid": "1", "subject": "s"}]}


def test_chat_requires_auth():
    client = TestClient(create_app(api_token="t"))
    resp = client.post("/chat", json={"question": "q"})
    assert resp.status_code == 401


def test_run_endpoint(monkeypatch):
    app = create_app(api_token="t")

    class FakeRunner:
        def __init__(self):
            self.called = False

        def run_main(self):
            self.called = True

    fake = FakeRunner()
    app.state.runner_factory = lambda: fake
    client = TestClient(app)
    resp = client.post("/run", headers={"Authorization": "Bearer t"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert fake.called is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_app.py::test_chat_endpoint -v`
Expected: FAIL with `404` (endpoint not defined) — assertion on status_code 200 fails.

- [ ] **Step 3: Write the implementation**

Replace `src/mailagent/api/app.py` with:
```python
from fastapi import FastAPI, Depends, HTTPException, Header, Body
from mailagent.api import routes


def create_app(api_token: str) -> FastAPI:
    app = FastAPI(title="Mailagent")
    app.state.api_token = api_token
    app.state.repo_factory = None
    app.state.runner_factory = None
    app.state.chat_factory = None

    def require_auth(authorization: str = Header(default="")):
        expected = f"Bearer {app.state.api_token}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/categories", dependencies=[Depends(require_auth)])
    def categories():
        return routes.list_categories(app.state.repo_factory())

    @app.post("/chat", dependencies=[Depends(require_auth)])
    def chat(question: str = Body(..., embed=True)):
        return routes.chat_answer(app.state.chat_factory(), question)

    @app.post("/run", dependencies=[Depends(require_auth)])
    def run():
        return routes.run_main(app.state.runner_factory())

    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/api/app.py tests/api/test_app.py
git commit -m "feat: add api chat and run endpoints"
```

---

## Task 17: API — history, audit, priorities endpoints

**Files:**
- Modify: `src/mailagent/api/app.py`
- Test: `tests/api/test_app.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/api/test_app.py`:
```python
def test_priorities_endpoint():
    app = create_app(api_token="t")

    class P:
        uid = "1"; priority = "high"; category = "X"

    class FakeRepo:
        def processed_by_priority(self):
            return [P()]

    app.state.repo_factory = lambda: FakeRepo()
    client = TestClient(app)
    resp = client.get("/priorities", headers={"Authorization": "Bearer t"})
    assert resp.status_code == 200
    assert resp.json() == [{"uid": "1", "priority": "high", "category": "X"}]


def test_history_and_audit_endpoints():
    app = create_app(api_token="t")

    class RunRow:
        run_type = "main"; uid = "1"; step = "classify"
        result = "success"; detail = "X"

    class AuditRow:
        actor = "scheduler"; action = "draft_append"
        target = "1"; result = "success"

    class FakeRepo:
        def recent_runs(self, limit):
            return [RunRow()]

        def recent_audit(self, limit):
            return [AuditRow()]

    app.state.repo_factory = lambda: FakeRepo()
    client = TestClient(app)
    h = client.get("/history?limit=5", headers={"Authorization": "Bearer t"})
    assert h.status_code == 200
    assert h.json()[0]["step"] == "classify"
    a = client.get("/audit", headers={"Authorization": "Bearer t"})
    assert a.status_code == 200
    assert a.json()[0]["action"] == "draft_append"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_app.py::test_priorities_endpoint -v`
Expected: FAIL with `404`.

- [ ] **Step 3: Write the implementation**

In `src/mailagent/api/app.py`, add these endpoints inside `create_app` (before `return app`):
```python
    @app.get("/priorities", dependencies=[Depends(require_auth)])
    def priorities():
        return routes.priorities(app.state.repo_factory())

    @app.get("/history", dependencies=[Depends(require_auth)])
    def history(limit: int = 50):
        return routes.recent_history(app.state.repo_factory(), limit)

    @app.get("/audit", dependencies=[Depends(require_auth)])
    def audit(limit: int = 50):
        return routes.recent_audit(app.state.repo_factory(), limit)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/api/app.py tests/api/test_app.py
git commit -m "feat: add api history, audit, priorities endpoints"
```

---

## Task 18: API — folder-mapping CRUD endpoints

**Files:**
- Modify: `src/mailagent/api/app.py`
- Test: `tests/api/test_app.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/api/test_app.py`:
```python
def test_mapping_endpoints():
    app = create_app(api_token="t")
    store = {}

    class M:
        def __init__(self, c, f):
            self.category_name = c; self.target_folder = f

    class FakeRepo:
        def list_mappings(self):
            return [M(c, f) for c, f in store.items()]

        def add_mapping(self, c, f):
            store[c] = f

        def remove_mapping(self, c):
            return store.pop(c, None) is not None

    app.state.repo_factory = lambda: FakeRepo()
    client = TestClient(app)
    h = {"Authorization": "Bearer t"}
    assert client.get("/mappings", headers=h).json() == []
    post = client.post("/mappings", json={"category": "N", "folder": "F"}, headers=h)
    assert post.status_code == 200
    assert client.get("/mappings", headers=h).json() == [{"category": "N", "folder": "F"}]
    delete = client.request("DELETE", "/mappings/N", headers=h)
    assert delete.json() == {"removed": True}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_app.py::test_mapping_endpoints -v`
Expected: FAIL with `404`.

- [ ] **Step 3: Write the implementation**

In `src/mailagent/api/app.py`, add these endpoints inside `create_app` (before `return app`):
```python
    @app.get("/mappings", dependencies=[Depends(require_auth)])
    def list_mappings():
        return routes.list_mappings(app.state.repo_factory())

    @app.post("/mappings", dependencies=[Depends(require_auth)])
    def add_mapping(category: str = Body(...), folder: str = Body(...)):
        return routes.add_mapping(app.state.repo_factory(), category, folder)

    @app.delete("/mappings/{category}", dependencies=[Depends(require_auth)])
    def remove_mapping(category: str):
        return routes.remove_mapping(app.state.repo_factory(), category)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/api/app.py tests/api/test_app.py
git commit -m "feat: add api folder-mapping crud endpoints"
```

---

## Task 19: Deployment — scheduler container + migration bootstrap

**Files:**
- Create: `docker-entrypoint.sh`
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `migrations/env.py`
- Modify: `.env.example`

This task has no unit test; verification is the build + an `alembic upgrade head` dry check in Task 20.

- [ ] **Step 1: Make migrations honor the env DATABASE_URL**

In `migrations/env.py`, add near the top (after `config = context.config`), so containerized migrations target the real DB host instead of the `alembic.ini` localhost default:
```python
import os
_db_url = os.environ.get("MAILAGENT_DATABASE_URL")
if _db_url:
    config.set_main_option("sqlalchemy.url", _db_url)
```

- [ ] **Step 2: Create the entrypoint script**

`docker-entrypoint.sh`:
```sh
#!/bin/sh
set -e
alembic upgrade head
exec "$@"
```

- [ ] **Step 3: Wire the entrypoint into the Dockerfile**

Replace `Dockerfile` with:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
COPY docker-entrypoint.sh ./
RUN pip install --no-cache-dir -e . && chmod +x docker-entrypoint.sh
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "mailagent.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 4: Add the scheduler service to docker-compose**

Replace `docker-compose.yml` with:
```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      POSTGRES_DB: mailagent
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
  app:
    build: .
    env_file: .env
    depends_on:
      - postgres
    ports:
      - "8000:8000"
  scheduler:
    build: .
    command: ["mailagent", "scheduler"]
    env_file: .env
    depends_on:
      - postgres
volumes:
  pgdata:
```

> Note: both `app` and `scheduler` run `alembic upgrade head` on start. Alembic
> no-ops when already at head; the brief startup race is acceptable for a
> single-user self-hosted deployment.

- [ ] **Step 5: Extend `.env.example`**

Replace `.env.example` with:
```
MAILAGENT_DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/mailagent
MAILAGENT_IMAP_HOST=imap.example.com
MAILAGENT_IMAP_USER=me@example.com
MAILAGENT_IMAP_PASSWORD=changeme
MAILAGENT_LLM_PROVIDER=openai
MAILAGENT_LLM_API_KEY=sk-...
MAILAGENT_SCHEDULE_MINUTES=15
MAILAGENT_FEEDBACK_MINUTES=60
MAILAGENT_STYLE_MINUTES=0
MAILAGENT_API_TOKEN=change-this-token
```

- [ ] **Step 6: Commit**

```bash
git add docker-entrypoint.sh Dockerfile docker-compose.yml migrations/env.py .env.example
git commit -m "chore: add scheduler container and migration bootstrap"
```

---

## Task 20: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v`
Expected: PASS — all tests across util, store, llm, imap, pipeline, learning, chat, scheduler (runner + loop), cli, api green. Postgres+pgvector and Greenmail containers start via pytest-docker.

- [ ] **Step 2: Verify the image builds**

Run: `docker compose build`
Expected: Build succeeds for `app` and `scheduler` (same image).

- [ ] **Step 3: Smoke-check the scheduler command is registered**

Run: `python -c "from typer.testing import CliRunner; from mailagent.cli.main import app; r = CliRunner().invoke(app, ['--help']); print(r.stdout)"`
Expected: Output lists `scheduler`, `chat`, `history`, `audit`, `priorities`, `add-mapping`, `mappings`, `remove-mapping`, `run-style`, `run-feedback`.

- [ ] **Step 4: Update the README**

In `README.md`, document the new commands and the scheduler container under usage:
- `docker compose up` now starts postgres, app, and scheduler; migrations run automatically on container start.
- CLI: `mailagent scheduler` (loop), `mailagent chat "..."`, `mailagent history`, `mailagent audit`, `mailagent priorities`, `mailagent add-mapping <cat> <folder>` / `mappings` / `remove-mapping`, `mailagent run-style` / `run-feedback`.
- API: `POST /chat`, `POST /run`, `GET /priorities`, `GET /history`, `GET /audit`, `GET/POST/DELETE /mappings` (all require `Authorization: Bearer <token>` except `/health`).

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: document milestone 2 cli/api surface and scheduler container"
```

---

## Self-Review Notes

- **Spec coverage:**
  - Periodic background run (own container) → Tasks 7, 10, 19.
  - Per-type cadence via `run_history` markers → Tasks 5, 6, 7.
  - Run-history per-mail step recording → Task 6.
  - Retry/backoff + per-mail isolation → Tasks 2, 3, 4 (+ existing `try/except` extended in Task 6).
  - CLI: chat, history, audit, priorities, mapping CRUD, run-style/run-feedback, scheduler → Tasks 10–14.
  - API: chat, run, priorities, history, audit, mapping CRUD → Tasks 15–18.
  - Deployment: scheduler service + `alembic upgrade head` bootstrap + env vars → Task 19.
  - Excluded by design (web frontend, local LLM, retention jobs, config-via-API) → not in plan, intentional.
- **Type consistency:** `record_run_step(run_type, uid, step, result, detail="")`,
  `last_run_at(run_type)`, `recent_runs(limit)`, `recent_audit(limit)`,
  `processed_by_priority()`, `add_mapping(category_name, target_folder)`,
  `list_mappings()`, `remove_mapping(category_name)` are defined in Tasks 5/8/9 and
  consumed identically in the CLI (10–14), routes (15), and API (16–18) tasks.
  `run_loop(build_runner_fn, intervals, *, clock, sleep, tick_seconds, max_cycles)`
  and `_due(last, now, minutes)` defined in Task 7, consumed in Task 10.
  `routes.chat_answer/run_main/recent_history/recent_audit/priorities/list_mappings/
  add_mapping/remove_mapping` defined in Task 15, consumed in Tasks 16–18.
  `Chat.ask -> ChatAnswer(text, sources=[ChatSource(uid, subject)])` matches the
  existing `chat/chat.py`.
- **Idempotency / isolation:** processed-UID guard unchanged; failed mails stay
  unprocessed and are recorded as `error` steps; whole-run never aborts on one mail.
