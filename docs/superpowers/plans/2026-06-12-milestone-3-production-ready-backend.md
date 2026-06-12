# Milestone 3 — Production-Ready Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the app to `mailbender`, make the deployed web API actually start, log the security-relevant audit events the spec requires, and close the production-readiness correctness gaps.

**Architecture:** Mechanical full rename `mailagent`→`mailbender` first, then feature work in the renamed package. A zero-arg `production_app()` factory (scoped-session + remove-after-request middleware) wires the existing injected API factories from `Config`. Audit instrumentation is added at the call sites that own a session (Runner, CLI commands, API endpoints). Correctness fixes: idempotent draft generation, retry on IMAP move/append, timestamps in history/audit output, and a Postgres healthcheck gate.

**Tech Stack:** Python 3.12, FastAPI, Typer, SQLAlchemy 2.x, Alembic, psycopg, pgvector, IMAPClient, pytest, pytest-docker (Postgres + GreenMail).

**Spec:** `docs/superpowers/specs/2026-06-12-milestone-3-production-ready-backend-design.md`

---

## File Structure (after the Task 1 rename, all paths are `mailbender`)

```
src/mailbender/
  config.py                 # MODIFY (T2): add api_token
  api/
    app.py                  # MODIFY (T9): audit helper + auth_failure/run/chat/mapping audit
    bootstrap.py            # CREATE (T3): production_app() factory
    routes.py               # MODIFY (T6): created_at in history/audit
  pipeline/draft_generator.py  # MODIFY (T4): duplicate-draft guard
  imap/client.py            # MODIFY (T5): retry on move/append
  scheduler/runner.py       # MODIFY (T7): provider_use + mail_moved audit
  cli/main.py               # MODIFY (T6,T8): created_at output + audit
Dockerfile                  # MODIFY (T3): CMD -> bootstrap:production_app
docker-compose.yml          # MODIFY (T10): postgres healthcheck + depends_on
tests/...                   # all import paths -> mailbender (T1); new/updated tests per task
```

Note: the historical M1/M2 specs/plans under `docs/superpowers/` keep their `mailagent` text (they document past milestones) — the rename sweep deliberately excludes `docs/`.

---

## Task 1: Rename mailagent → mailbender

**Files:** the `src/mailagent/` package, all of `tests/`, `pyproject.toml`, `alembic.ini`, `migrations/`, `Dockerfile`, `docker-entrypoint.sh`, `docker-compose.yml`, `tests/docker-compose.test.yml`, `.env.example`, `README.md`.

This is a mechanical refactor verified by the existing suite (no new unit test), like M2's deployment task.

- [ ] **Step 1: Move the package directory (preserve history)**

```bash
git mv src/mailagent src/mailbender
```

- [ ] **Step 2: Sweep-replace all three casings across code, config, and docs (excluding docs/, .venv, .git)**

```bash
grep -rIl --exclude-dir=.git --exclude-dir=.venv --exclude-dir=docs \
  --exclude-dir=.pytest_cache --exclude-dir='*.egg-info' \
  -e mailagent -e MAILAGENT -e Mailagent . \
  | xargs perl -pi -e 's/mailagent/mailbender/g; s/MAILAGENT/MAILBENDER/g; s/Mailagent/Mailbender/g'
```

This converts: package imports (`mailagent.*`→`mailbender.*`), the env prefix
(`MAILAGENT_`→`MAILBENDER_`), the DB names (`mailagent`→`mailbender`,
`mailagent_test`→`mailbender_test`), the FastAPI title (`Mailagent`→`Mailbender`),
the `[project.scripts]` entry, and the `uvicorn`/`command` references.

- [ ] **Step 3: Verify no stray references remain (outside docs/)**

```bash
grep -rI --exclude-dir=.git --exclude-dir=.venv --exclude-dir=docs --exclude-dir=.pytest_cache -e mailagent -e MAILAGENT -e Mailagent . || echo "clean"
```
Expected: `clean`

- [ ] **Step 4: Reinstall the package (name + entry point changed) and run the full suite**

```bash
pip install -e ".[dev]"
pytest -q
```
Expected: all tests pass (same count as before, ~90), now importing `mailbender`. The `mailbender` console script is installed; the old `mailagent` script is gone.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: rename application mailagent -> mailbender"
```

---

## Task 2: Config — api_token field

**Files:**
- Modify: `src/mailbender/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:
```python
def test_api_token_from_env(monkeypatch):
    monkeypatch.setenv("MAILBENDER_DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("MAILBENDER_IMAP_HOST", "h")
    monkeypatch.setenv("MAILBENDER_IMAP_USER", "u")
    monkeypatch.setenv("MAILBENDER_IMAP_PASSWORD", "p")
    monkeypatch.setenv("MAILBENDER_API_TOKEN", "secret-token")
    from mailbender.config import load_config
    cfg = load_config()
    assert cfg.api_token.get_secret_value() == "secret-token"


def test_api_token_defaults_none(monkeypatch):
    monkeypatch.setenv("MAILBENDER_DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("MAILBENDER_IMAP_HOST", "h")
    monkeypatch.setenv("MAILBENDER_IMAP_USER", "u")
    monkeypatch.setenv("MAILBENDER_IMAP_PASSWORD", "p")
    from mailbender.config import load_config
    cfg = load_config()
    assert cfg.api_token is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_api_token_from_env -v`
Expected: FAIL with `AttributeError: 'Config' object has no attribute 'api_token'`

- [ ] **Step 3: Write the implementation**

In `src/mailbender/config.py`, add a field to `Config` (after `llm_api_key`):
```python
    llm_api_key: SecretStr | None = None
    api_token: SecretStr | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailbender/config.py tests/test_config.py
git commit -m "feat: add api_token to config"
```

---

## Task 3: API production bootstrap

**Files:**
- Create: `src/mailbender/api/bootstrap.py`
- Modify: `Dockerfile`
- Test: `tests/api/test_bootstrap.py`

- [ ] **Step 1: Write the failing test**

`tests/api/test_bootstrap.py`:
```python
from pydantic import SecretStr


def test_production_app_wires_factories_and_token(monkeypatch):
    import mailbender.api.bootstrap as bs

    class FakeCfg:
        database_url = "postgresql+psycopg://u:p@localhost/db"
        api_token = SecretStr("tok")

    monkeypatch.setattr(bs, "load_config", lambda: FakeCfg())
    monkeypatch.setattr(bs, "make_engine", lambda url: object())

    app = bs.production_app()
    assert app.state.api_token == "tok"
    assert app.state.repo_factory is not None
    assert app.state.runner_factory is not None
    assert app.state.chat_factory is not None


def test_production_app_empty_token_when_unset(monkeypatch):
    import mailbender.api.bootstrap as bs

    class FakeCfg:
        database_url = "postgresql+psycopg://u:p@localhost/db"
        api_token = None

    monkeypatch.setattr(bs, "load_config", lambda: FakeCfg())
    monkeypatch.setattr(bs, "make_engine", lambda url: object())

    app = bs.production_app()
    assert app.state.api_token == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_bootstrap.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailbender.api.bootstrap'`

- [ ] **Step 3: Write the implementation**

`src/mailbender/api/bootstrap.py`:
```python
from sqlalchemy.orm import scoped_session, sessionmaker
from mailbender.config import load_config
from mailbender.store.db import make_engine
from mailbender.store.repository import Repository
from mailbender.api.app import create_app


def _build_imap(cfg):
    from mailbender.imap.client import ImapClient
    return ImapClient(
        host=cfg.imap.host, port=cfg.imap.port, user=cfg.imap.user,
        password=cfg.imap.password.get_secret_value(),
        drafts_folder=cfg.imap.drafts_folder, sent_folder=cfg.imap.sent_folder,
    )


def _build_provider(cfg):
    from mailbender.llm.factory import make_provider
    api_key = cfg.llm_api_key.get_secret_value() if cfg.llm_api_key else None
    return make_provider(cfg.llm_provider, api_key)


def _build_chat(cfg, session):
    from mailbender.chat.chat import Chat
    return Chat(_build_provider(cfg), session)


def _build_runner(cfg, session):
    from mailbender.scheduler.wiring import build_runner
    return build_runner(session, _build_imap(cfg), _build_provider(cfg))


def production_app():
    """Zero-arg app factory for `uvicorn --factory`.

    Reads Config, wires the API's injected factories to a request-scoped
    session, and removes the session after each request so connections don't
    leak. This is the production entrypoint; tests use create_app directly.
    """
    cfg = load_config()
    engine = make_engine(cfg.database_url)
    SessionLocal = scoped_session(
        sessionmaker(bind=engine, expire_on_commit=False))
    token = cfg.api_token.get_secret_value() if cfg.api_token else ""
    app = create_app(api_token=token)

    app.state.repo_factory = lambda: Repository(SessionLocal())
    app.state.chat_factory = lambda: _build_chat(cfg, SessionLocal())
    app.state.runner_factory = lambda: _build_runner(cfg, SessionLocal())

    @app.middleware("http")
    async def _remove_session(request, call_next):
        try:
            return await call_next(request)
        finally:
            SessionLocal.remove()

    return app
```

In `Dockerfile`, change the `CMD` from `mailbender.api.app:create_app` to the production factory:
```dockerfile
CMD ["uvicorn", "mailbender.api.bootstrap:production_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_bootstrap.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailbender/api/bootstrap.py Dockerfile tests/api/test_bootstrap.py
git commit -m "feat: add production app factory wiring api sessions"
```

---

## Task 4: Duplicate-draft guard

**Files:**
- Modify: `src/mailbender/pipeline/draft_generator.py`
- Test: `tests/pipeline/test_draft_generator.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/pipeline/test_draft_generator.py`:
```python
def test_generate_is_idempotent_for_same_uid(session):
    imap = FakeImap()
    gen = DraftGenerator(FakeLLMProvider(draft="Hallo."), imap, session)
    email = Email(uid="dup-1", subject="Frage", sender="a@b.c", body="?",
                  message_id="<m1>")
    gen.generate(email, style_examples=[])
    gen.generate(email, style_examples=[])  # second call must be a no-op
    assert len(imap.drafts) == 1
    refs = session.execute(select(ReferenceDraft)).scalars().all()
    assert len(refs) == 1
```
(`FakeImap`, `FakeLLMProvider`, `Email`, `DraftGenerator`, `ReferenceDraft`,
`select`, and the `session` fixture are already imported/defined in this file.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/test_draft_generator.py::test_generate_is_idempotent_for_same_uid -v`
Expected: FAIL — second call appends a second draft / second `ReferenceDraft` (asserts see 2, not 1).

- [ ] **Step 3: Write the implementation**

Replace `src/mailbender/pipeline/draft_generator.py` with:
```python
from sqlalchemy import select
from mailbender.llm.provider import LLMProvider, Email
from mailbender.store.models import ReferenceDraft


class DraftGenerator:
    def __init__(self, provider: LLMProvider, imap_client, session):
        self.provider = provider
        self.imap = imap_client
        self.session = session

    def generate(self, email: Email, style_examples: list[str]) -> str:
        existing = self.session.execute(
            select(ReferenceDraft).where(ReferenceDraft.source_uid == email.uid)
        ).scalar_one_or_none()
        if existing is not None:
            # Already drafted for this mail (e.g. a prior run committed the
            # reference but failed before mark_processed). Don't append again.
            return existing.content
        content = self.provider.generate_draft(email, style_examples)
        subject = email.subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        self.imap.append_draft(subject, content)
        self.session.add(ReferenceDraft(
            source_uid=email.uid,
            message_id=email.message_id,
            content=content,
        ))
        self.session.commit()
        return content
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipeline/test_draft_generator.py -v`
Expected: PASS (all draft-generator tests)

- [ ] **Step 5: Commit**

```bash
git add src/mailbender/pipeline/draft_generator.py tests/pipeline/test_draft_generator.py
git commit -m "fix: make draft generation idempotent per source uid"
```

---

## Task 5: Retry on IMAP move and append

**Files:**
- Modify: `src/mailbender/imap/client.py`
- Test: `tests/imap/test_client.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/imap/test_client.py` (pure unit test — no GreenMail container needed):
```python
def test_move_retries_transient_failure(monkeypatch):
    import mailbender.imap.client as mod

    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    state = {"move": 0}

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def select_folder(self, folder):
            pass

        def move(self, uids, target):
            state["move"] += 1
            if state["move"] < 2:
                raise OSError("temporary")

    client = mod.ImapClient(host="h", port=1, user="u", password="p", use_ssl=False)
    monkeypatch.setattr(client, "_connect", lambda: FakeConn())
    client.move("5", "Archive")
    assert state["move"] == 2


def test_append_retries_transient_failure(monkeypatch):
    import mailbender.imap.client as mod

    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    state = {"append": 0}

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def append(self, folder, data):
            state["append"] += 1
            if state["append"] < 2:
                raise OSError("temporary")

    client = mod.ImapClient(host="h", port=1, user="u", password="p", use_ssl=False)
    monkeypatch.setattr(client, "_connect", lambda: FakeConn())
    client.append_draft("Subject", "Body", folder="Drafts")
    assert state["append"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/imap/test_client.py::test_move_retries_transient_failure -v`
Expected: FAIL with `OSError: temporary` (the operation is not yet retried, so the first failure propagates).

- [ ] **Step 3: Write the implementation**

In `src/mailbender/imap/client.py`, replace the `append_draft` and `move` methods with retry-wrapped operations (keep imports `time` and `retry` that already exist at the top):
```python
    def append_draft(self, subject: str, body: str, folder: str | None = None):
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.user
        msg.set_content(body)
        target = folder or self.drafts_folder
        with self._connect() as c:
            retry(lambda: c.append(target, msg.as_bytes()), sleep=time.sleep)

    def move(self, uid: str, target_folder: str, source_folder="INBOX"):
        with self._connect() as c:
            c.select_folder(source_folder)
            retry(lambda: c.move([int(uid)], target_folder), sleep=time.sleep)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/imap/test_client.py -v`
Expected: PASS (new unit tests pass; the GreenMail integration tests still pass since the happy path is unchanged)

- [ ] **Step 5: Commit**

```bash
git add src/mailbender/imap/client.py tests/imap/test_client.py
git commit -m "fix: retry imap move and append operations"
```

---

## Task 6: Timestamps in history/audit output

**Files:**
- Modify: `src/mailbender/api/routes.py`
- Modify: `src/mailbender/cli/main.py`
- Test: `tests/api/test_app.py`, `tests/cli/test_main.py`

- [ ] **Step 1: Write/adjust the failing tests**

In `tests/api/test_app.py`, REPLACE `test_history_and_audit_endpoints` with a version whose fake rows carry timestamps and that asserts `created_at` is serialized:
```python
def test_history_and_audit_endpoints():
    from datetime import datetime
    app = create_app(api_token="t")
    ts = datetime(2026, 6, 12, 9, 30, 0)

    class RunRow:
        run_type = "main"; uid = "1"; step = "classify"
        result = "success"; detail = "X"; created_at = ts

    class AuditRow:
        actor = "scheduler"; action = "draft_append"
        target = "1"; result = "success"; created_at = ts

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
    assert h.json()[0]["created_at"] == "2026-06-12T09:30:00"
    a = client.get("/audit", headers={"Authorization": "Bearer t"})
    assert a.status_code == 200
    assert a.json()[0]["action"] == "draft_append"
    assert a.json()[0]["created_at"] == "2026-06-12T09:30:00"
```

In `tests/cli/test_main.py`, REPLACE the `Row` classes in `test_history_command` and `test_audit_command` so they carry a `created_at` datetime (the CLI now prints it):
```python
def test_history_command(monkeypatch):
    from datetime import datetime
    from mailbender.cli import main

    class Row:
        run_type = "main"; uid = "1"; step = "classify"
        result = "success"; detail = "Newsletter"
        created_at = datetime(2026, 6, 12, 9, 30, 0)

    class FakeRepo:
        def recent_runs(self, limit=50):
            return [Row()]

    monkeypatch.setattr(main, "_make_repo", lambda: FakeRepo())
    result = runner.invoke(app, ["history"])
    assert result.exit_code == 0
    assert "classify" in result.stdout
    assert "2026-06-12" in result.stdout


def test_audit_command(monkeypatch):
    from datetime import datetime
    from mailbender.cli import main

    class Row:
        actor = "scheduler"; action = "draft_append"
        target = "uid-1"; result = "success"
        created_at = datetime(2026, 6, 12, 9, 30, 0)

    class FakeRepo:
        def recent_audit(self, limit=50):
            return [Row()]

    monkeypatch.setattr(main, "_make_repo", lambda: FakeRepo())
    result = runner.invoke(app, ["audit"])
    assert result.exit_code == 0
    assert "draft_append" in result.stdout
    assert "2026-06-12" in result.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/test_app.py::test_history_and_audit_endpoints tests/cli/test_main.py::test_history_command -v`
Expected: FAIL — API response has no `created_at` key (KeyError/assert), and the CLI output lacks the date.

- [ ] **Step 3: Write the implementation**

In `src/mailbender/api/routes.py`, add a helper and include `created_at` in both serializers:
```python
def _iso(dt):
    return dt.isoformat() if dt else None


def recent_history(repo, limit: int) -> list[dict]:
    return [
        {"run_type": r.run_type, "uid": r.uid, "step": r.step,
         "result": r.result, "detail": r.detail,
         "created_at": _iso(r.created_at)}
        for r in repo.recent_runs(limit)
    ]


def recent_audit(repo, limit: int) -> list[dict]:
    return [
        {"actor": r.actor, "action": r.action, "target": r.target,
         "result": r.result, "created_at": _iso(r.created_at)}
        for r in repo.recent_audit(limit)
    ]
```

In `src/mailbender/cli/main.py`, prefix the `history` and `audit` output lines with the timestamp:
```python
@app.command()
def history(limit: int = 50):
    """Show recent run history."""
    repo = _make_repo()
    for r in repo.recent_runs(limit):
        typer.echo(f"{r.created_at:%Y-%m-%d %H:%M} {r.run_type:8} "
                   f"{str(r.uid):8} {r.step:10} {r.result:8} {r.detail}")


@app.command()
def audit(limit: int = 50):
    """Show recent audit-log entries."""
    repo = _make_repo()
    for r in repo.recent_audit(limit):
        typer.echo(f"{r.created_at:%Y-%m-%d %H:%M} {r.actor:10} "
                   f"{r.action:16} {r.target:12} {r.result}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/test_app.py tests/cli/test_main.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add src/mailbender/api/routes.py src/mailbender/cli/main.py tests/api/test_app.py tests/cli/test_main.py
git commit -m "feat: include timestamps in history and audit output"
```

---

## Task 7: Runner audit — provider_use and mail_moved

**Files:**
- Modify: `src/mailbender/scheduler/runner.py`
- Test: `tests/scheduler/test_runner.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/scheduler/test_runner.py`:
```python
def test_main_run_audits_provider_use_and_move(session):
    from sqlalchemy import select
    from mailbender.store.models import AuditLog
    inbox = [Email(uid="1", subject="Frage", sender="a@b.c", body="?",
                   message_id="<m1>")]
    imap = FakeImap(inbox)
    provider = FakeLLMProvider(category="Newsletter", priority="low")
    runner = Runner(
        imap=imap, provider=provider, session=session,
        categories=["Newsletter"], mapping={"Newsletter": "Archive/News"},
        reply_category="Antwort nötig", style_examples=[],
    )
    runner.run_main()
    actions = [r.action for r in session.execute(select(AuditLog)).scalars().all()]
    assert "mail_moved" in actions
    assert "provider_use" in actions
```
(The existing module-level `FakeImap` records moves; `mapping` routes "Newsletter" to a folder so a move happens.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scheduler/test_runner.py::test_main_run_audits_provider_use_and_move -v`
Expected: FAIL — no `mail_moved` / `provider_use` audit rows are written.

- [ ] **Step 3: Write the implementation**

In `src/mailbender/scheduler/runner.py`:

Store the provider name in `__init__` (add one line at the end of `__init__`):
```python
        self.provider_name = type(provider).__name__
```

In `run_main`, after a successful move, add an audit record. Change the move block from:
```python
                moved = self.mover.maybe_move(email.uid, category)
                self.repo.record_run_step("main", email.uid, "move",
                                          "success" if moved else "skipped")
```
to:
```python
                moved = self.mover.maybe_move(email.uid, category)
                self.repo.record_run_step("main", email.uid, "move",
                                          "success" if moved else "skipped")
                if moved:
                    self.audit.record("scheduler", "mail_moved", email.uid)
```

Add a coarse provider-usage audit at the end of each run method. In `run_main`, after the loop, alongside the existing run marker:
```python
        self.repo.record_run_step("main", None, "run", "success")
        self.audit.record("scheduler", "provider_use", self.provider_name)
```
In `run_style`:
```python
    def run_style(self):
        StyleLearner(self.imap, self.session).bootstrap()
        self.repo.record_run_step("style", None, "run", "success")
        self.audit.record("scheduler", "provider_use", self.provider_name)
```
In `run_feedback`:
```python
    def run_feedback(self):
        FeedbackLearner(self.imap, self.session).run()
        self.repo.record_run_step("feedback", None, "run", "success")
        self.audit.record("scheduler", "provider_use", self.provider_name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/scheduler/test_runner.py tests/scheduler/test_runner_extra.py -v`
Expected: PASS (all scheduler runner tests)

- [ ] **Step 5: Commit**

```bash
git add src/mailbender/scheduler/runner.py tests/scheduler/test_runner.py
git commit -m "feat: audit provider use per run and mailbox moves"
```

---

## Task 8: CLI audit — runs, chat, config changes

**Files:**
- Modify: `src/mailbender/cli/main.py`
- Test: `tests/cli/test_main.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/cli/test_main.py`:
```python
def test_add_category_audits(monkeypatch):
    from mailbender.cli import main

    recorded = []

    class FakeRepo:
        session = object()

        def add_category(self, name, description=""):
            pass

    class FakeAuditor:
        def __init__(self, session):
            pass

        def record(self, actor, action, target="", result="success"):
            recorded.append((actor, action, target))

    monkeypatch.setattr(main, "_make_repo", lambda: FakeRepo())
    monkeypatch.setattr(main, "AuditLogger", FakeAuditor)
    result = runner.invoke(app, ["add-category", "Rechnung"])
    assert result.exit_code == 0
    assert ("cli", "category_add", "Rechnung") in recorded


def test_run_command_audits(monkeypatch):
    from mailbender.cli import main

    recorded = []

    class FakeRunner:
        session = object()

        def run_main(self):
            pass

    class FakeAuditor:
        def __init__(self, session):
            pass

        def record(self, actor, action, target="", result="success"):
            recorded.append((actor, action, target))

    monkeypatch.setattr(main, "_make_runner", lambda: FakeRunner())
    monkeypatch.setattr(main, "AuditLogger", FakeAuditor)
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 0
    assert ("cli", "run_triggered", "main") in recorded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cli/test_main.py::test_add_category_audits -v`
Expected: FAIL — `main` has no `AuditLogger` attribute / no audit recorded.

- [ ] **Step 3: Write the implementation**

In `src/mailbender/cli/main.py`, import `AuditLogger` at module top (below the existing imports) so it is monkeypatchable as `main.AuditLogger`:
```python
from mailbender.audit.log import AuditLogger
```

The `Runner` exposes its session as `self.session` and `Repository` as `self.repo`; the chat object exposes `self.session` and `self.provider`. Add audit calls to the relevant commands. Replace these commands:
```python
@app.command("add-category")
def add_category(name: str, description: str = ""):
    """Add a category."""
    repo = _make_repo()
    repo.add_category(name, description)
    AuditLogger(repo.session).record("cli", "category_add", name)
    typer.echo(f"Added category: {name}")


@app.command("remove-category")
def remove_category(name: str):
    """Remove a category by name."""
    repo = _make_repo()
    removed = repo.remove_category(name)
    AuditLogger(repo.session).record(
        "cli", "category_remove", name, "success" if removed else "error")
    if removed:
        typer.echo(f"Removed category: {name}")
    else:
        typer.echo(f"No such category: {name}")
        raise typer.Exit(code=1)


@app.command("add-mapping")
def add_mapping(category: str, folder: str):
    """Map a category to a target IMAP folder (upserts)."""
    repo = _make_repo()
    repo.add_mapping(category, folder)
    AuditLogger(repo.session).record("cli", "mapping_add", category)
    typer.echo(f"Mapped {category} -> {folder}")


@app.command("remove-mapping")
def remove_mapping(category: str):
    """Remove a category-to-folder mapping."""
    repo = _make_repo()
    removed = repo.remove_mapping(category)
    AuditLogger(repo.session).record(
        "cli", "mapping_remove", category, "success" if removed else "error")
    if removed:
        typer.echo(f"Removed mapping: {category}")
    else:
        typer.echo(f"No such mapping: {category}")
        raise typer.Exit(code=1)


@app.command()
def run():
    """Trigger a main run now."""
    runner = _make_runner()
    AuditLogger(runner.session).record("cli", "run_triggered", "main")
    runner.run_main()
    typer.echo("Main run complete.")


@app.command("run-style")
def run_style():
    """Bootstrap the writing-style profile from the Sent folder now."""
    runner = _make_runner()
    AuditLogger(runner.session).record("cli", "run_triggered", "style")
    runner.run_style()
    typer.echo("Style run complete.")


@app.command("run-feedback")
def run_feedback():
    """Run the draft-vs-sent feedback pass now."""
    runner = _make_runner()
    AuditLogger(runner.session).record("cli", "run_triggered", "feedback")
    runner.run_feedback()
    typer.echo("Feedback run complete.")


@app.command()
def chat(question: str):
    """Ask a question about the mailbox."""
    chat_obj = _make_chat()
    answer = chat_obj.ask(question)
    auditor = AuditLogger(chat_obj.session)
    auditor.record("cli", "chat_query")
    auditor.record("cli", "provider_use", type(chat_obj.provider).__name__)
    typer.echo(answer.text)
    if answer.sources:
        typer.echo("Quellen:")
        for s in answer.sources:
            typer.echo(f"  [{s.uid}] {s.subject}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/cli/test_main.py -v`
Expected: PASS (all CLI tests)

- [ ] **Step 5: Commit**

```bash
git add src/mailbender/cli/main.py tests/cli/test_main.py
git commit -m "feat: audit cli runs, chat queries, and config changes"
```

---

## Task 9: API audit — auth failures, runs, chat, mapping changes

**Files:**
- Modify: `src/mailbender/api/app.py`
- Test: `tests/api/test_app.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/api/test_app.py`:
```python
def test_auth_failure_is_audited(monkeypatch):
    import mailbender.api.app as appmod
    app = create_app(api_token="t")
    recorded = []

    class FakeAuditor:
        def __init__(self, session):
            pass

        def record(self, actor, action, target="", result="success"):
            recorded.append((actor, action, result))

    class FakeRepo:
        session = object()

    app.state.repo_factory = lambda: FakeRepo()
    monkeypatch.setattr(appmod, "AuditLogger", FakeAuditor)
    client = TestClient(app)
    resp = client.get("/categories")  # no token
    assert resp.status_code == 401
    assert ("web", "auth_failure", "error") in recorded


def test_auth_failure_without_repo_factory_does_not_crash():
    # repo_factory is None (default) -> auditing is skipped, still 401
    client = TestClient(create_app(api_token="t"))
    assert client.get("/categories").status_code == 401


def test_run_endpoint_is_audited(monkeypatch):
    import mailbender.api.app as appmod
    app = create_app(api_token="t")
    recorded = []

    class FakeAuditor:
        def __init__(self, session):
            pass

        def record(self, actor, action, target="", result="success"):
            recorded.append((actor, action, target))

    class FakeRunner:
        session = object()

        def run_main(self):
            pass

    class FakeRepo:
        session = object()

    app.state.repo_factory = lambda: FakeRepo()
    app.state.runner_factory = lambda: FakeRunner()
    monkeypatch.setattr(appmod, "AuditLogger", FakeAuditor)
    client = TestClient(app)
    resp = client.post("/run", headers={"Authorization": "Bearer t"})
    assert resp.status_code == 200
    assert ("web", "run_triggered", "main") in recorded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_app.py::test_auth_failure_is_audited -v`
Expected: FAIL — no audit recorded on 401 (and `appmod.AuditLogger` does not exist yet).

- [ ] **Step 3: Write the implementation**

In `src/mailbender/api/app.py`, import `AuditLogger` at module top and add an `_audit` helper that is a no-op when no repo factory is wired (keeps the existing token-only 401 tests passing). Then instrument the endpoints. Update the file to:
```python
from fastapi import FastAPI, Depends, HTTPException, Header, Body
from mailbender.api import routes
from mailbender.audit.log import AuditLogger


def _audit(app, actor, action, target="", result="success"):
    factory = app.state.repo_factory
    if factory is None:
        return
    AuditLogger(factory().session).record(actor, action, target, result)


def create_app(api_token: str) -> FastAPI:
    app = FastAPI(title="Mailbender")
    app.state.api_token = api_token
    app.state.repo_factory = None
    app.state.runner_factory = None
    app.state.chat_factory = None

    def require_auth(authorization: str = Header(default="")):
        expected = f"Bearer {app.state.api_token}"
        if authorization != expected:
            _audit(app, "web", "auth_failure", result="error")
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/categories", dependencies=[Depends(require_auth)])
    def categories():
        return routes.list_categories(app.state.repo_factory())

    @app.post("/chat", dependencies=[Depends(require_auth)])
    def chat(question: str = Body(..., embed=True)):
        chat_obj = app.state.chat_factory()
        _audit(app, "web", "chat_query")
        _audit(app, "web", "provider_use", type(chat_obj.provider).__name__)
        return routes.chat_answer(chat_obj, question)

    @app.post("/run", dependencies=[Depends(require_auth)])
    def run():
        _audit(app, "web", "run_triggered", "main")
        return routes.run_main(app.state.runner_factory())

    @app.get("/priorities", dependencies=[Depends(require_auth)])
    def priorities():
        return routes.priorities(app.state.repo_factory())

    @app.get("/history", dependencies=[Depends(require_auth)])
    def history(limit: int = 50):
        return routes.recent_history(app.state.repo_factory(), limit)

    @app.get("/audit", dependencies=[Depends(require_auth)])
    def audit(limit: int = 50):
        return routes.recent_audit(app.state.repo_factory(), limit)

    @app.get("/mappings", dependencies=[Depends(require_auth)])
    def list_mappings():
        return routes.list_mappings(app.state.repo_factory())

    @app.post("/mappings", dependencies=[Depends(require_auth)])
    def add_mapping(category: str = Body(...), folder: str = Body(...)):
        result = routes.add_mapping(app.state.repo_factory(), category, folder)
        _audit(app, "web", "mapping_add", category)
        return result

    @app.delete("/mappings/{category}", dependencies=[Depends(require_auth)])
    def remove_mapping(category: str):
        result = routes.remove_mapping(app.state.repo_factory(), category)
        _audit(app, "web", "mapping_remove", category)
        return result

    return app
```
Note: the `_audit` helper reads `AuditLogger` from module scope, so tests can replace `mailbender.api.app.AuditLogger` to capture calls. The chat endpoint reads `chat_obj.provider` (the `Chat` object exposes `self.provider`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_app.py -v`
Expected: PASS (all API tests, including the pre-existing 401/endpoint tests)

- [ ] **Step 5: Commit**

```bash
git add src/mailbender/api/app.py tests/api/test_app.py
git commit -m "feat: audit api auth failures, runs, chat, and mapping changes"
```

---

## Task 10: docker-compose Postgres healthcheck

**Files:**
- Modify: `docker-compose.yml`

No unit test (compose config). Verified by `docker compose config` and the Task 11 build.

- [ ] **Step 1: Add a healthcheck and gate app/scheduler on it**

Replace `docker-compose.yml` with:
```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      POSTGRES_DB: mailbender
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d mailbender"]
      interval: 5s
      timeout: 3s
      retries: 10
  app:
    build: .
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "8000:8000"
  scheduler:
    build: .
    command: ["mailbender", "scheduler"]
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
volumes:
  pgdata:
```

- [ ] **Step 2: Validate the compose file**

Run: `docker compose config >/dev/null && echo OK`
Expected: `OK` (compose file parses; `depends_on` conditions are valid)

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: gate app and scheduler on postgres healthcheck"
```

---

## Task 11: Full verification and docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run the full suite**

Run: `pytest -q`
Expected: PASS — all tests green (M2's ~90 plus the M3 additions), now under the `mailbender` package.

- [ ] **Step 2: Verify the images build and the production factory imports**

```bash
docker compose build
python -c "import mailbender.api.bootstrap as b; print('factory:', b.production_app.__name__)"
```
Expected: build succeeds for `app` and `scheduler`; prints `factory: production_app`.

- [ ] **Step 3: Update the README**

In `README.md` (already `mailbender` after Task 1), adjust the Quick start so it no longer tells the user to run migrations manually (the entrypoint does it) and reflects the working API:
- `docker compose up -d` starts postgres (with healthcheck), app, and scheduler; migrations run automatically on container start once Postgres is healthy.
- Set `MAILBENDER_API_TOKEN` in `.env`; the API requires `Authorization: Bearer $MAILBENDER_API_TOKEN` on all endpoints except `GET /health`.
- Note that the audit log (`mailbender audit` / `GET /audit`) records auth failures, config changes, manual runs, chat queries, and mailbox writes.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update readme for mailbender rename and production api"
```

---

## Self-Review Notes

- **Spec coverage:**
  - Rename mailagent→mailbender (full: package/imports/CLI/env-prefix/DB/Docker/docs) → Task 1.
  - API production bootstrap (api_token in Config, zero-arg `production_app`, scoped session + remove middleware, Dockerfile CMD) → Tasks 2, 3.
  - Audit completeness: auth failures (T9), config changes categories/mappings (T8 CLI, T9 API), runs (T8 CLI, T9 API), chat queries (T8, T9), coarse provider_use per run/chat (T7 runner, T8/T9 chat), mailbox move (T7), draft_append (already present) → Tasks 7, 8, 9.
  - Timestamps in history/audit output → Task 6.
  - Duplicate-draft guard → Task 4; retry on move/append → Task 5; Postgres healthcheck gate → Task 10.
  - Deferred (M4/M5): web frontend, login-success logging, retention/cleanup, local LLM provider, feedback References/subject match, style dedup → not in plan, intentional.
- **Type consistency:** `Config.api_token: SecretStr | None`; `production_app()` zero-arg; `_build_imap/_build_provider/_build_chat/_build_runner(cfg[, session])` defined and used in T3; `AuditLogger(session).record(actor, action, target="", result="success")` (existing signature) used identically in Runner (T7), CLI (T8), and API `_audit` (T9); `Runner.provider_name`, `Runner.session`, `Repository` exposed as `runner.repo`, `Chat.session`/`Chat.provider` all match existing code; `routes.recent_history/recent_audit` add `created_at` consumed by `tests/api/test_app.py` (T6).
- **Idempotency/isolation:** draft guard keyed on `source_uid`; audit writes never abort a run (they follow successful actions or the existing per-mail try/except); `_audit` is a no-op when `repo_factory` is None so token-only 401 tests stay green.
