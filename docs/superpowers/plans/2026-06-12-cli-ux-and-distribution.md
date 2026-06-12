# CLI UX & Distribution (Thin Client) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the thick container-only CLI into a pip-installable thin HTTP client (`mailbender`) that talks to the self-hosted API, with guided `login`, Rich output plus a global `--json`, while server-only ops (the scheduler loop) move to a separate `mailbender-server` script behind a `[server]` extra.

**Architecture:** Add a `mailbender.client` package (config resolution, httpx wrapper, Rich/JSON rendering). Rewrite `mailbender.cli` as a thin client that imports only `mailbender.client.*` + typer/rich/httpx. Move the `scheduler` command to a new `mailbender.server_cli`. Extend the M3 API with category-mutation endpoints and a `run_type` body on `POST /run` so the thin client covers the operator workflow. Split `pyproject.toml` into thin base deps + a heavy `[server]` extra, with two console scripts.

**Tech Stack:** Python 3.12, Typer, httpx, Rich, tomllib/tomli-w (client); FastAPI + SQLAlchemy + the M3 server stack (server extra); pytest, httpx.MockTransport, pytest-docker.

**Spec:** `docs/superpowers/specs/2026-06-12-cli-ux-and-distribution-design.md`

---

## File Structure

```
src/mailbender/
  api/app.py            # MODIFY (T1,T2): category endpoints; run_type on POST /run
  api/routes.py         # MODIFY (T1,T2): add_category/remove_category/seed_categories; run() run_type
  client/               # CREATE — thin client (httpx/rich/tomli only; NEVER server modules)
    __init__.py
    config.py           # CREATE (T3): ClientConfig + resolve/save/delete + config_path
    api.py              # CREATE (T4): ApiClient httpx wrapper + ApiError translation
    render.py           # CREATE (T5): emit_json + Rich tables/panel/confirm
  cli/main.py           # REWRITE (T7,T8): thin client root + command groups
  server_cli/           # CREATE (T6): host-only ops
    __init__.py
    main.py             # CREATE (T6): scheduler command (moved from cli/main.py)
pyproject.toml          # MODIFY (T10): base deps + [server] extra + two scripts
Dockerfile              # MODIFY (T11): install .[server]
docker-compose.yml      # MODIFY (T11): scheduler command -> mailbender-server
README.md               # MODIFY (T11): CLI section
tests/
  api/test_app.py       # MODIFY (T1,T2): new endpoint tests
  client/               # CREATE: test_config.py, test_api.py, test_render.py
  cli/test_main.py      # REPLACE (T7,T8): thin-client tests via MockTransport
  cli/test_import_boundary.py  # CREATE (T9)
  server_cli/test_main.py      # CREATE (T6): scheduler test (moved)
```

**Hard module rule:** `mailbender.cli.*` imports only `mailbender.client.*`, `mailbender` (`__version__`), and stdlib/typer/rich/httpx — never `store`, `imap`, `api`, `scheduler`, `llm`, `pipeline`, `config`. The Task 9 guard test enforces this.

---

## Task 1: API — category mutation endpoints

**Files:**
- Modify: `src/mailbender/api/routes.py`
- Modify: `src/mailbender/api/app.py`
- Test: `tests/api/test_app.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/api/test_app.py`:
```python
def test_category_endpoints(monkeypatch):
    import mailbender.api.app as appmod
    app = create_app(api_token="t")
    recorded = []
    store = {"Newsletter": "news"}

    class FakeAuditor:
        def __init__(self, session): pass
        def record(self, actor, action, target="", result="success"):
            recorded.append((action, target, result))

    class C:
        def __init__(self, name): self.name = name

    class FakeRepo:
        session = object()
        def list_categories(self): return [C(n) for n in store]
        def add_category(self, name, description=""): store[name] = description
        def remove_category(self, name): return store.pop(name, None) is not None

    app.state.repo_factory = lambda: FakeRepo()
    monkeypatch.setattr(appmod, "AuditLogger", FakeAuditor)
    monkeypatch.setattr(appmod, "seed_default_categories", lambda repo: 3)
    client = TestClient(app)
    h = {"Authorization": "Bearer t"}

    assert client.post("/categories", json={"name": "Rechnung"}, headers=h).status_code == 200
    assert ("category_add", "Rechnung", "success") in recorded
    assert client.delete("/categories/Rechnung", headers=h).json() == {"removed": True}
    assert ("category_remove", "Rechnung", "success") in recorded
    miss = client.delete("/categories/Nope", headers=h)
    assert miss.status_code == 404
    seed = client.post("/categories/seed", headers=h)
    assert seed.json() == {"added": 3}
    assert ("category_seed", "", "success") in recorded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_app.py::test_category_endpoints -v`
Expected: FAIL — `POST /categories` returns 404 (route missing) / `appmod.seed_default_categories` doesn't exist.

- [ ] **Step 3: Write the implementation**

In `src/mailbender/api/routes.py`, add:
```python
def add_category(repo, name: str, description: str = "") -> dict:
    repo.add_category(name, description)
    return {"name": name, "description": description}


def remove_category(repo, name: str) -> bool:
    return repo.remove_category(name)
```
(Seeding has no route helper — the endpoint calls the module-level
`seed_default_categories` directly so tests can monkeypatch one seam.)

In `src/mailbender/api/app.py`, import the seed helper at module top so it is monkeypatchable, and add the endpoints. Add below the existing imports:
```python
from mailbender.categories import seed_default_categories
```
Add these endpoints inside `create_app` (before `return app`):
```python
    @app.post("/categories", dependencies=[Depends(require_auth)])
    def create_category(name: str = Body(...), description: str = Body("")):
        result = routes.add_category(app.state.repo_factory(), name, description)
        _audit(app, "web", "category_add", name)
        return result

    @app.delete("/categories/{name}", dependencies=[Depends(require_auth)])
    def delete_category(name: str):
        removed = routes.remove_category(app.state.repo_factory(), name)
        if not removed:
            _audit(app, "web", "category_remove", name, "error")
            raise HTTPException(status_code=404, detail="No such category")
        _audit(app, "web", "category_remove", name)
        return {"removed": True}

    @app.post("/categories/seed", dependencies=[Depends(require_auth)])
    def seed_categories_endpoint():
        result = seed_default_categories(app.state.repo_factory())
        _audit(app, "web", "category_seed")
        return {"added": result}
```
Note: `seed_categories_endpoint` calls the module-level `seed_default_categories` (monkeypatchable in tests) directly rather than going through `routes.seed_categories` (which imports it locally), keeping one seam.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_app.py -v`
Expected: PASS (all api tests)

- [ ] **Step 5: Commit**

```bash
git add src/mailbender/api/routes.py src/mailbender/api/app.py tests/api/test_app.py
git commit -m "feat: add category mutation api endpoints"
```

---

## Task 2: API — run_type on POST /run

**Files:**
- Modify: `src/mailbender/api/routes.py`
- Modify: `src/mailbender/api/app.py`
- Test: `tests/api/test_app.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/api/test_app.py`:
```python
def test_run_endpoint_dispatches_run_type(monkeypatch):
    import mailbender.api.app as appmod
    app = create_app(api_token="t")
    called = []
    recorded = []

    class FakeAuditor:
        def __init__(self, session): pass
        def record(self, actor, action, target="", result="success"):
            recorded.append((action, target))

    class FakeRunner:
        session = object()
        def run_main(self): called.append("main")
        def run_style(self): called.append("style")
        def run_feedback(self): called.append("feedback")

    class FakeRepo:
        session = object()

    app.state.repo_factory = lambda: FakeRepo()
    app.state.runner_factory = lambda: FakeRunner()
    monkeypatch.setattr(appmod, "AuditLogger", FakeAuditor)
    client = TestClient(app)
    h = {"Authorization": "Bearer t"}

    assert client.post("/run", headers=h).json() == {"status": "ok", "run_type": "main"}
    assert client.post("/run", json={"run_type": "style"}, headers=h).status_code == 200
    assert called == ["main", "style"]
    assert ("run_triggered", "style") in recorded
    bad = client.post("/run", json={"run_type": "bogus"}, headers=h)
    assert bad.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_app.py::test_run_endpoint_dispatches_run_type -v`
Expected: FAIL — `/run` ignores `run_type` (always run_main; response lacks `run_type`; no 422 on bad value).

- [ ] **Step 3: Write the implementation**

In `src/mailbender/api/routes.py`, replace `run_main` with a dispatching `run`:
```python
RUN_TYPES = {"main", "style", "feedback"}


def run(runner, run_type: str = "main") -> dict:
    dispatch = {
        "main": runner.run_main,
        "style": runner.run_style,
        "feedback": runner.run_feedback,
    }
    dispatch[run_type]()
    return {"status": "ok", "run_type": run_type}
```

In `src/mailbender/api/app.py`, replace the `/run` endpoint with one that validates and passes `run_type`:
```python
    @app.post("/run", dependencies=[Depends(require_auth)])
    def run(run_type: str = Body("main", embed=True)):
        if run_type not in routes.RUN_TYPES:
            raise HTTPException(status_code=422, detail="invalid run_type")
        _audit(app, "web", "run_triggered", run_type)
        return routes.run(app.state.runner_factory(), run_type)
```

- [ ] **Step 4: Update the M3 run-audit test for the new response shape**

The M3 test `test_run_endpoint_is_audited` posts `/run` with no body and asserts `("web","run_triggered","main")` was recorded and `run_main` ran. That still holds (default `main`). No change needed unless it asserted the exact response body `{"status": "ok"}`; if so, update that assertion to `{"status": "ok", "run_type": "main"}`. Read the test and adjust only that assertion if present.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/api/test_app.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add src/mailbender/api/routes.py src/mailbender/api/app.py tests/api/test_app.py
git commit -m "feat: support run_type on the run endpoint"
```

---

## Task 3: client/config.py — config resolution & file I/O

**Files:**
- Create: `src/mailbender/client/__init__.py`
- Create: `src/mailbender/client/config.py`
- Create: `tests/client/__init__.py`
- Test: `tests/client/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/client/__init__.py`: (empty file)

`tests/client/test_config.py`:
```python
import stat
from pathlib import Path
from mailbender.client.config import (
    ClientConfig, resolve_config, save_config, delete_config,
)


def _write(tmp_path, body):
    p = tmp_path / "config.toml"
    p.write_text(body)
    return p


def test_resolution_order_flag_beats_env_beats_file(tmp_path):
    p = _write(tmp_path, 'url = "http://file"\ntoken = "file-tok"\n')
    env = {"MAILBENDER_API_URL": "http://env", "MAILBENDER_API_TOKEN": "env-tok"}
    # file only
    c = resolve_config(env={}, path=p)
    assert c.url == "http://file" and c.token == "file-tok"
    # env beats file
    c = resolve_config(env=env, path=p)
    assert c.url == "http://env" and c.token == "env-tok"
    # flag beats env
    c = resolve_config(flag_url="http://flag", flag_token="flag-tok", env=env, path=p)
    assert c.url == "http://flag" and c.token == "flag-tok"


def test_missing_everything_yields_none(tmp_path):
    c = resolve_config(env={}, path=tmp_path / "nope.toml")
    assert c.url is None and c.token is None


def test_save_writes_chmod_600_and_delete(tmp_path):
    p = tmp_path / "config.toml"
    save_config(ClientConfig(url="http://x", token="tok"), path=p)
    assert resolve_config(env={}, path=p) == ClientConfig(url="http://x", token="tok")
    mode = stat.S_IMODE(p.stat().st_mode)
    assert mode == 0o600
    assert delete_config(path=p) is True
    assert delete_config(path=p) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/client/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailbender.client'`

- [ ] **Step 3: Write the implementation**

`src/mailbender/client/__init__.py`: (empty file)

`src/mailbender/client/config.py`:
```python
import os
import stat
import tomllib
from dataclasses import dataclass
from pathlib import Path

import tomli_w


@dataclass
class ClientConfig:
    url: str | None = None
    token: str | None = None


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "mailbender" / "config.toml"


def _read_file(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def resolve_config(flag_url=None, flag_token=None, env=None, path=None) -> ClientConfig:
    env = os.environ if env is None else env
    path = config_path() if path is None else path
    data = _read_file(path)
    url = flag_url or env.get("MAILBENDER_API_URL") or data.get("url")
    token = flag_token or env.get("MAILBENDER_API_TOKEN") or data.get("token")
    return ClientConfig(url=url, token=token)


def save_config(cfg: ClientConfig, path=None) -> Path:
    path = config_path() if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        tomli_w.dump({"url": cfg.url or "", "token": cfg.token or ""}, f)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    return path


def delete_config(path=None) -> bool:
    path = config_path() if path is None else path
    if path.exists():
        path.unlink()
        return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/client/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailbender/client/__init__.py src/mailbender/client/config.py tests/client
git commit -m "feat: add thin-client config resolution"
```

---

## Task 4: client/api.py — httpx client + error translation

**Files:**
- Create: `src/mailbender/client/api.py`
- Test: `tests/client/test_api.py`

- [ ] **Step 1: Write the failing test**

`tests/client/test_api.py`:
```python
import httpx
import pytest
from mailbender.client.config import ClientConfig
from mailbender.client.api import ApiClient, ApiError, NotConfigured


def _client(handler):
    transport = httpx.MockTransport(handler)
    return ApiClient(ClientConfig(url="http://api", token="tok"), transport=transport)


def test_requires_url_and_token():
    with pytest.raises(NotConfigured):
        ApiClient(ClientConfig(url=None, token=None))


def test_chat_hits_post_with_question_and_bearer():
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        import json
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"text": "A", "sources": []})

    with _client(handler) as c:
        out = c.chat("hi")
    assert out == {"text": "A", "sources": []}
    assert seen["method"] == "POST" and seen["path"] == "/chat"
    assert seen["auth"] == "Bearer tok"
    assert seen["body"] == {"question": "hi"}


def test_run_sends_run_type():
    seen = {}

    def handler(request):
        import json
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "ok", "run_type": "style"})

    with _client(handler) as c:
        c.run("style")
    assert seen["body"] == {"run_type": "style"}


def test_401_translates_to_friendly_error():
    def handler(request):
        return httpx.Response(401, json={"detail": "Unauthorized"})

    with _client(handler) as c:
        with pytest.raises(ApiError) as exc:
            c.priorities()
    assert "login" in str(exc.value).lower()


def test_connect_error_translates():
    def handler(request):
        raise httpx.ConnectError("refused")

    with _client(handler) as c:
        with pytest.raises(ApiError) as exc:
            c.priorities()
    assert "unreachable" in str(exc.value).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/client/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailbender.client.api'`

- [ ] **Step 3: Write the implementation**

`src/mailbender/client/api.py`:
```python
import httpx


class ApiError(Exception):
    def __init__(self, message: str, *, exit_code: int = 1):
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


class NotConfigured(ApiError):
    pass


class ApiClient:
    def __init__(self, config, *, transport=None, timeout: float = 10.0):
        if not config.url or not config.token:
            raise NotConfigured(
                "Not logged in — run `mailbender login` "
                "(or set MAILBENDER_API_URL/MAILBENDER_API_TOKEN).")
        self._url = config.url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._url,
            headers={"Authorization": f"Bearer {config.token}"},
            timeout=timeout, transport=transport)

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _request(self, method, path, **kw):
        try:
            resp = self._client.request(method, path, **kw)
        except httpx.ConnectError:
            raise ApiError(
                f"API unreachable at {self._url} — is the server running?")
        except httpx.HTTPError as exc:
            raise ApiError(f"request failed: {exc}")
        if resp.status_code == 401:
            raise ApiError("unauthorized — run `mailbender login` again.")
        if resp.status_code == 404:
            raise ApiError("not found (404).")
        if resp.status_code >= 500:
            raise ApiError(f"server error ({resp.status_code}): {resp.text}")
        if resp.status_code >= 400:
            raise ApiError(f"request rejected ({resp.status_code}): {resp.text}")
        return resp

    def health(self):
        return self._request("GET", "/health").json()

    def chat(self, question):
        return self._request("POST", "/chat", json={"question": question}).json()

    def run(self, run_type="main"):
        return self._request("POST", "/run", json={"run_type": run_type}).json()

    def priorities(self):
        return self._request("GET", "/priorities").json()

    def history(self, limit=50):
        return self._request("GET", "/history", params={"limit": limit}).json()

    def audit(self, limit=50):
        return self._request("GET", "/audit", params={"limit": limit}).json()

    def categories_list(self):
        return self._request("GET", "/categories").json()

    def categories_add(self, name, description=""):
        return self._request("POST", "/categories",
                             json={"name": name, "description": description}).json()

    def categories_remove(self, name):
        return self._request("DELETE", f"/categories/{name}").json()

    def categories_seed(self):
        return self._request("POST", "/categories/seed").json()

    def mappings_list(self):
        return self._request("GET", "/mappings").json()

    def mappings_add(self, category, folder):
        return self._request("POST", "/mappings",
                             json={"category": category, "folder": folder}).json()

    def mappings_remove(self, category):
        return self._request("DELETE", f"/mappings/{category}").json()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/client/test_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailbender/client/api.py tests/client/test_api.py
git commit -m "feat: add thin-client http api wrapper"
```

---

## Task 5: client/render.py — JSON and Rich output

**Files:**
- Create: `src/mailbender/client/render.py`
- Test: `tests/client/test_render.py`

- [ ] **Step 1: Write the failing test**

`tests/client/test_render.py`:
```python
import json
from mailbender.client import render


def test_emit_json_writes_parsable_json(capsys):
    render.emit_json({"a": 1, "b": [2, 3]})
    out = capsys.readouterr().out
    assert json.loads(out) == {"a": 1, "b": [2, 3]}


def test_table_prints_rows(capsys):
    render.table("Cats", ["name"], [["Newsletter"], ["Rechnung"]])
    out = capsys.readouterr().out
    assert "Newsletter" in out and "Rechnung" in out


def test_priorities_human_shows_values(capsys):
    render.priorities([{"uid": "1", "priority": "high", "category": "X"}], as_json=False)
    out = capsys.readouterr().out
    assert "high" in out and "X" in out


def test_priorities_json(capsys):
    rows = [{"uid": "1", "priority": "high", "category": "X"}]
    render.priorities(rows, as_json=True)
    assert json.loads(capsys.readouterr().out) == rows


def test_chat_shows_text_and_sources(capsys):
    render.chat({"text": "Sarah approved", "sources": [{"uid": "1", "subject": "Budget"}]},
                as_json=False)
    out = capsys.readouterr().out
    assert "Sarah approved" in out and "Budget" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/client/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailbender.client.render'`

- [ ] **Step 3: Write the implementation**

`src/mailbender/client/render.py`:
```python
import json as _json
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# JSON to stdout; human chatter/errors to stderr so pipes stay clean.
_out = Console()
_err = Console(stderr=True)


def emit_json(data) -> None:
    sys.stdout.write(_json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def error(message: str) -> None:
    _err.print(f"[red]error:[/] {message}")


def confirm(message: str) -> None:
    _out.print(f"[green]{message}[/]")


def table(title: str, columns: list[str], rows: list[list[str]]) -> None:
    t = Table(title=title)
    for col in columns:
        t.add_column(col)
    for row in rows:
        t.add_row(*[str(c) for c in row])
    _out.print(t)


_PRIO_STYLE = {"high": "red", "medium": "yellow", "low": "dim"}


def priorities(rows, as_json: bool) -> None:
    if as_json:
        emit_json(rows)
        return
    t = Table(title="Priorities")
    t.add_column("priority"); t.add_column("uid"); t.add_column("category")
    for r in rows:
        style = _PRIO_STYLE.get(r.get("priority"), "")
        prio = f"[{style}]{r.get('priority')}[/]" if style else str(r.get("priority"))
        t.add_row(prio, str(r.get("uid")), str(r.get("category")))
    _out.print(t)


def history(rows, as_json: bool) -> None:
    if as_json:
        emit_json(rows)
        return
    table("Run history", ["created_at", "run_type", "uid", "step", "result", "detail"],
          [[r.get("created_at"), r.get("run_type"), r.get("uid"),
            r.get("step"), r.get("result"), r.get("detail")] for r in rows])


def audit(rows, as_json: bool) -> None:
    if as_json:
        emit_json(rows)
        return
    table("Audit log", ["created_at", "actor", "action", "target", "result"],
          [[r.get("created_at"), r.get("actor"), r.get("action"),
            r.get("target"), r.get("result")] for r in rows])


def categories(names, as_json: bool) -> None:
    if as_json:
        emit_json(names)
        return
    table("Categories", ["name"], [[n] for n in names])


def mappings(rows, as_json: bool) -> None:
    if as_json:
        emit_json(rows)
        return
    table("Mappings", ["category", "folder"],
          [[r.get("category"), r.get("folder")] for r in rows])


def chat(answer, as_json: bool) -> None:
    if as_json:
        emit_json(answer)
        return
    _out.print(Panel(answer.get("text", ""), title="Answer"))
    sources = answer.get("sources") or []
    if sources:
        table("Sources", ["uid", "subject"],
              [[s.get("uid"), s.get("subject")] for s in sources])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/client/test_render.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailbender/client/render.py tests/client/test_render.py
git commit -m "feat: add thin-client rich/json renderers"
```

---

## Task 6: server_cli — move the scheduler command

**Files:**
- Create: `src/mailbender/server_cli/__init__.py`
- Create: `src/mailbender/server_cli/main.py`
- Modify: `src/mailbender/cli/main.py` (remove `scheduler` + its `run_loop` import)
- Create: `tests/server_cli/__init__.py`
- Test: `tests/server_cli/test_main.py`
- Modify: `tests/cli/test_main.py` (remove the scheduler test moved here)

- [ ] **Step 1: Write the failing test**

`tests/server_cli/__init__.py`: (empty file)

`tests/server_cli/test_main.py`:
```python
from typer.testing import CliRunner
from mailbender.server_cli.main import app

runner = CliRunner()


def test_scheduler_command_invokes_run_loop(monkeypatch):
    from mailbender.server_cli import main

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/server_cli/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailbender.server_cli'`

- [ ] **Step 3: Write the implementation**

`src/mailbender/server_cli/__init__.py`: (empty file)

`src/mailbender/server_cli/main.py`:
```python
import typer
from mailbender.scheduler.loop import run_loop

app = typer.Typer(help="Mailbender server-side operations")


def _load_config():
    from mailbender.config import load_config
    return load_config()


def _make_session(cfg):
    from mailbender.store.db import make_engine, make_session_factory
    engine = make_engine(cfg.database_url)
    return make_session_factory(engine)()


def _make_runner():
    from mailbender.imap.client import ImapClient
    from mailbender.llm.factory import make_provider
    from mailbender.scheduler.wiring import build_runner
    cfg = _load_config()
    session = _make_session(cfg)
    imap = ImapClient(
        host=cfg.imap.host, port=cfg.imap.port, user=cfg.imap.user,
        password=cfg.imap.password.get_secret_value(),
        drafts_folder=cfg.imap.drafts_folder, sent_folder=cfg.imap.sent_folder,
    )
    api_key = cfg.llm_api_key.get_secret_value() if cfg.llm_api_key else None
    provider = make_provider(cfg.llm_provider, api_key)
    return build_runner(session, imap, provider)


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


if __name__ == "__main__":
    app()
```

In `src/mailbender/cli/main.py`, delete the `scheduler` command (lines defining `def scheduler()`), and delete the now-unused `from mailbender.scheduler.loop import run_loop` import. (The thick CLI's other commands stay for now; they are fully replaced in Tasks 7–8.) In `tests/cli/test_main.py`, delete `test_scheduler_command_invokes_run_loop` (it now lives in the server_cli test).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/server_cli/test_main.py tests/cli/test_main.py -v`
Expected: PASS (scheduler test passes under server_cli; cli tests pass without the moved test)

- [ ] **Step 5: Commit**

```bash
git add src/mailbender/server_cli tests/server_cli src/mailbender/cli/main.py tests/cli/test_main.py
git commit -m "feat: move scheduler command to mailbender-server cli"
```

---

## Task 7: Thin CLI core — root app, global options, auth commands

**Files:**
- Modify (rewrite): `src/mailbender/cli/main.py`
- Replace: `tests/cli/test_main.py`

This task replaces the thick `cli/main.py` with the thin client's root app, global flags, the `_client_factory` seam, and the `login`/`logout`/`status`/`version` commands. The API-calling command groups arrive in Task 8.

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `tests/cli/test_main.py` with:
```python
import json
import httpx
import pytest
from typer.testing import CliRunner
from mailbender.cli import main
from mailbender.cli.main import app
from mailbender.client.config import ClientConfig

runner = CliRunner()


def _patch_client(monkeypatch, handler):
    def factory(cfg):
        from mailbender.client.api import ApiClient
        return ApiClient(ClientConfig(url="http://api", token="tok"),
                         transport=httpx.MockTransport(handler))
    monkeypatch.setattr(main, "_client_factory", factory)


def test_version_is_local():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_status_reports_url_and_token_presence(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "resolve_config",
                        lambda **kw: ClientConfig(url="http://api", token="tok"))

    def handler(request):
        return httpx.Response(200, json={"status": "ok"})

    _patch_client(monkeypatch, handler)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "http://api" in result.stdout
    assert "tok" not in result.stdout  # token value never printed


def test_login_writes_config_with_flags(monkeypatch, tmp_path):
    path = tmp_path / "config.toml"
    monkeypatch.setattr(main, "config_path", lambda: path)

    def handler(request):
        return httpx.Response(200, json={"status": "ok"})

    _patch_client(monkeypatch, handler)
    result = runner.invoke(
        app, ["login", "--url", "http://api", "--token", "tok"])
    assert result.exit_code == 0
    assert path.exists()
    import tomllib
    data = tomllib.loads(path.read_text())
    assert data["url"] == "http://api" and data["token"] == "tok"


def test_logout_removes_config(monkeypatch, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('url = "x"\ntoken = "y"\n')
    monkeypatch.setattr(main, "config_path", lambda: path)
    result = runner.invoke(app, ["logout"])
    assert result.exit_code == 0
    assert not path.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/cli/test_main.py::test_version_is_local -v`
Expected: FAIL — the rewritten module/commands don't exist yet (import error or missing command).

- [ ] **Step 3: Write the implementation**

Replace the entire contents of `src/mailbender/cli/main.py` with:
```python
import typer
from rich.console import Console

from mailbender import __version__
from mailbender.client import render
from mailbender.client.config import (
    ClientConfig, resolve_config, save_config, delete_config, config_path,
)
from mailbender.client.api import ApiClient, ApiError

app = typer.Typer(help="Mailbender CLI — a thin client for the self-hosted API.")


class Ctx:
    def __init__(self, json=False, url=None, token=None, verbose=False):
        self.json = json
        self.url = url
        self.token = token
        self.verbose = verbose


def _version_callback(value: bool):
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    json: bool = typer.Option(False, "--json", help="Emit raw JSON for scripting."),
    url: str = typer.Option(None, "--url", help="API base URL (overrides config/env)."),
    token: str = typer.Option(None, "--token", help="API token (overrides config/env)."),
    verbose: bool = typer.Option(False, "--verbose", help="Show tracebacks on error."),
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True,
        help="Show version and exit."),
):
    ctx.obj = Ctx(json=json, url=url, token=token, verbose=verbose)


def _client_factory(cfg: ClientConfig) -> ApiClient:
    return ApiClient(cfg)


def _api(ctx: typer.Context, fn):
    """Resolve config, build the client, call fn(client), translate errors."""
    o: Ctx = ctx.obj
    try:
        cfg = resolve_config(flag_url=o.url, flag_token=o.token)
        with _client_factory(cfg) as client:
            return fn(client)
    except ApiError as exc:
        render.error(exc.message)
        if o.verbose:
            raise
        raise typer.Exit(code=exc.exit_code)


@app.command()
def version():
    """Print the client version."""
    typer.echo(__version__)


@app.command()
def login(
    url: str = typer.Option(None, "--url"),
    token: str = typer.Option(None, "--token"),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip reachability/token check."),
):
    """Configure the API URL and token (writes ~/.config/mailbender/config.toml)."""
    url = url or typer.prompt("API URL", default="http://localhost:8000")
    token = token or typer.prompt("API token", hide_input=True)
    cfg = ClientConfig(url=url, token=token)
    if not no_verify:
        try:
            with _client_factory(cfg) as client:
                client.health()          # reachability
                client.categories_list()  # token check (401 if wrong)
        except ApiError as exc:
            render.error(f"login failed: {exc.message}")
            raise typer.Exit(code=1)
    path = save_config(cfg, path=config_path())
    typer.echo(f"Saved credentials to {path}")


@app.command()
def logout():
    """Remove the stored credentials."""
    if delete_config(path=config_path()):
        typer.echo("Logged out.")
    else:
        typer.echo("No stored credentials.")


@app.command()
def status(ctx: typer.Context):
    """Show the resolved API URL, whether a token is set, and reachability."""
    o: Ctx = ctx.obj
    cfg = resolve_config(flag_url=o.url, flag_token=o.token)
    reachable = False
    if cfg.url and cfg.token:
        try:
            with _client_factory(cfg) as client:
                client.health()
                reachable = True
        except ApiError:
            reachable = False
    info = {"url": cfg.url, "token_set": bool(cfg.token), "reachable": reachable}
    if o.json:
        render.emit_json(info)
    else:
        Console().print(
            f"url: {cfg.url or '(unset)'}\n"
            f"token: {'set' if cfg.token else 'unset'}\n"
            f"reachable: {reachable}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/cli/test_main.py -v`
Expected: PASS (version, status, login, logout tests all green)

- [ ] **Step 5: Commit**

```bash
git add src/mailbender/cli/main.py tests/cli/test_main.py
git commit -m "feat: rewrite cli as thin client (root, auth, status commands)"
```

---

## Task 8: Thin CLI commands — API command groups + rendering

**Files:**
- Modify: `src/mailbender/cli/main.py`
- Modify: `tests/cli/test_main.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/cli/test_main.py`:
```python
def test_priorities_renders_human(monkeypatch):
    monkeypatch.setattr(main, "resolve_config",
                        lambda **kw: ClientConfig(url="http://api", token="tok"))

    def handler(request):
        assert request.url.path == "/priorities"
        return httpx.Response(200, json=[{"uid": "1", "priority": "high", "category": "X"}])

    _patch_client(monkeypatch, handler)
    result = runner.invoke(app, ["priorities"])
    assert result.exit_code == 0
    assert "high" in result.stdout


def test_priorities_json(monkeypatch):
    monkeypatch.setattr(main, "resolve_config",
                        lambda **kw: ClientConfig(url="http://api", token="tok"))
    rows = [{"uid": "1", "priority": "high", "category": "X"}]

    def handler(request):
        return httpx.Response(200, json=rows)

    _patch_client(monkeypatch, handler)
    result = runner.invoke(app, ["--json", "priorities"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == rows


def test_run_sends_type(monkeypatch):
    monkeypatch.setattr(main, "resolve_config",
                        lambda **kw: ClientConfig(url="http://api", token="tok"))
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "ok", "run_type": "style"})

    _patch_client(monkeypatch, handler)
    result = runner.invoke(app, ["run", "--type", "style"])
    assert result.exit_code == 0
    assert seen["body"] == {"run_type": "style"}


def test_categories_add(monkeypatch):
    monkeypatch.setattr(main, "resolve_config",
                        lambda **kw: ClientConfig(url="http://api", token="tok"))
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(200, json={"name": "Rechnung", "description": ""})

    _patch_client(monkeypatch, handler)
    result = runner.invoke(app, ["categories", "add", "Rechnung"])
    assert result.exit_code == 0
    assert seen["method"] == "POST" and seen["path"] == "/categories"


def test_chat_renders(monkeypatch):
    monkeypatch.setattr(main, "resolve_config",
                        lambda **kw: ClientConfig(url="http://api", token="tok"))

    def handler(request):
        return httpx.Response(200, json={"text": "Sarah approved", "sources": []})

    _patch_client(monkeypatch, handler)
    result = runner.invoke(app, ["chat", "what did sarah say?"])
    assert result.exit_code == 0
    assert "Sarah approved" in result.stdout


def test_unconfigured_api_command_exits_nonzero(monkeypatch):
    monkeypatch.setattr(main, "resolve_config",
                        lambda **kw: ClientConfig(url=None, token=None))
    result = runner.invoke(app, ["priorities"])
    assert result.exit_code != 0
    assert "login" in (result.stdout + result.stderr).lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/cli/test_main.py::test_priorities_renders_human -v`
Expected: FAIL — `priorities` command not defined yet.

- [ ] **Step 3: Write the implementation**

In `src/mailbender/cli/main.py`, add the API-calling commands and the two sub-apps (place above `if __name__ == "__main__":`):
```python
@app.command()
def chat(ctx: typer.Context, question: str):
    """Ask a question about the mailbox."""
    data = _api(ctx, lambda c: c.chat(question))
    render.chat(data, ctx.obj.json)


@app.command()
def run(ctx: typer.Context,
        type: str = typer.Option("main", "--type", help="main|style|feedback")):
    """Trigger a run now."""
    data = _api(ctx, lambda c: c.run(type))
    if ctx.obj.json:
        render.emit_json(data)
    else:
        render.confirm(f"{data.get('run_type', type)} run triggered.")


@app.command()
def priorities(ctx: typer.Context):
    """List processed mail sorted by priority."""
    data = _api(ctx, lambda c: c.priorities())
    render.priorities(data, ctx.obj.json)


@app.command()
def history(ctx: typer.Context, limit: int = typer.Option(50, "--limit")):
    """Show recent run history."""
    data = _api(ctx, lambda c: c.history(limit))
    render.history(data, ctx.obj.json)


@app.command()
def audit(ctx: typer.Context, limit: int = typer.Option(50, "--limit")):
    """Show recent audit-log entries."""
    data = _api(ctx, lambda c: c.audit(limit))
    render.audit(data, ctx.obj.json)


categories_app = typer.Typer(help="Manage categories.")
app.add_typer(categories_app, name="categories")


@categories_app.command("list")
def categories_list(ctx: typer.Context):
    """List configured categories."""
    data = _api(ctx, lambda c: c.categories_list())
    render.categories(data, ctx.obj.json)


@categories_app.command("add")
def categories_add(ctx: typer.Context, name: str,
                   description: str = typer.Option("", "--description")):
    """Add a category."""
    data = _api(ctx, lambda c: c.categories_add(name, description))
    if ctx.obj.json:
        render.emit_json(data)
    else:
        render.confirm(f"Added category: {name}")


@categories_app.command("remove")
def categories_remove(ctx: typer.Context, name: str):
    """Remove a category."""
    data = _api(ctx, lambda c: c.categories_remove(name))
    if ctx.obj.json:
        render.emit_json(data)
    else:
        render.confirm(f"Removed category: {name}")


@categories_app.command("seed")
def categories_seed(ctx: typer.Context):
    """Add the default category set (idempotent)."""
    data = _api(ctx, lambda c: c.categories_seed())
    if ctx.obj.json:
        render.emit_json(data)
    else:
        render.confirm(f"Seeded {data.get('added', 0)} categories.")


mappings_app = typer.Typer(help="Manage category-to-folder mappings.")
app.add_typer(mappings_app, name="mappings")


@mappings_app.command("list")
def mappings_list(ctx: typer.Context):
    """List category-to-folder mappings."""
    data = _api(ctx, lambda c: c.mappings_list())
    render.mappings(data, ctx.obj.json)


@mappings_app.command("add")
def mappings_add(ctx: typer.Context, category: str, folder: str):
    """Map a category to a target IMAP folder."""
    data = _api(ctx, lambda c: c.mappings_add(category, folder))
    if ctx.obj.json:
        render.emit_json(data)
    else:
        render.confirm(f"Mapped {category} -> {folder}")


@mappings_app.command("remove")
def mappings_remove(ctx: typer.Context, category: str):
    """Remove a category-to-folder mapping."""
    data = _api(ctx, lambda c: c.mappings_remove(category))
    if ctx.obj.json:
        render.emit_json(data)
    else:
        render.confirm(f"Removed mapping: {category}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/cli/test_main.py -v`
Expected: PASS (all, including `test_unconfigured_api_command_exits_nonzero` from Task 7)

- [ ] **Step 5: Commit**

```bash
git add src/mailbender/cli/main.py tests/cli/test_main.py
git commit -m "feat: add thin-client command groups (chat/run/priorities/categories/mappings)"
```

---

## Task 9: Import-boundary guard test

**Files:**
- Create: `tests/cli/test_import_boundary.py`

- [ ] **Step 1: Write the failing test**

`tests/cli/test_import_boundary.py`:
```python
import sys


def test_thin_cli_does_not_import_server_modules():
    # Drop any server modules a previous test imported, then import the CLI.
    server_prefixes = (
        "mailbender.store", "mailbender.imap", "mailbender.api",
        "mailbender.scheduler", "mailbender.llm", "mailbender.pipeline",
        "mailbender.config", "mailbender.chat", "mailbender.audit",
    )
    for name in list(sys.modules):
        if name.startswith(server_prefixes):
            del sys.modules[name]
    if "mailbender.cli.main" in sys.modules:
        del sys.modules["mailbender.cli.main"]

    import mailbender.cli.main  # noqa: F401

    leaked = [n for n in sys.modules if n.startswith(server_prefixes)]
    assert leaked == [], f"thin CLI imported server modules: {leaked}"
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `pytest tests/cli/test_import_boundary.py -v`
Expected: PASS if Tasks 6–8 fully removed server imports from `cli/main.py`. If it FAILS, the failure lists exactly which server module leaked — fix `cli/main.py`/`client/*` to stop importing it (the only allowed imports are `mailbender` (`__version__`), `mailbender.client.*`, typer, rich, httpx, stdlib), then re-run until green.

- [ ] **Step 3: (only if it failed) Remove the offending import, re-run**

Adjust the imports flagged by the test until `leaked == []`.

- [ ] **Step 4: Commit**

```bash
git add tests/cli/test_import_boundary.py
git commit -m "test: enforce thin-cli import boundary"
```

---

## Task 10: Packaging — split base/server deps + two scripts

**Files:**
- Modify: `pyproject.toml`

This is a config change verified by reinstall + the full suite. (CI runs `pip install -e ".[dev]"`; making `dev` pull the `server` extra keeps CI working with no workflow edit.)

- [ ] **Step 1: Rewrite the dependency + scripts sections**

In `pyproject.toml`, replace the `dependencies`, `[project.optional-dependencies]`, and `[project.scripts]` sections with:
```toml
dependencies = [
    "typer>=0.12",
    "httpx>=0.27",
    "rich>=13.0",
    "tomli-w>=1.0",
]

[project.optional-dependencies]
server = [
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "psycopg[binary]>=3.1",
    "pgvector>=0.2.5",
    "imapclient>=3.0",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "openai>=1.0",
]
dev = [
    "mailbender[server]",
    "pytest>=8.0",
    "pytest-docker>=3.1",
    "ruff>=0.4",
]

[project.scripts]
mailbender        = "mailbender.cli.main:app"
mailbender-server = "mailbender.server_cli.main:app"
```

- [ ] **Step 2: Reinstall with the dev (server-inclusive) extra**

Run: `pip install -e ".[dev]"`
Expected: installs the thin base deps plus the server extra (via `mailbender[server]`) plus test tools; both `mailbender` and `mailbender-server` console scripts are registered.

- [ ] **Step 3: Verify both entry points resolve and the suite is green**

```bash
mailbender --version
mailbender-server --help
pytest -q
```
Expected: `mailbender --version` prints `0.1.0`; `mailbender-server --help` lists `scheduler`; full suite passes.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: split thin base deps and server extra with two scripts"
```

---

## Task 11: Docker, compose, and README

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `README.md`

- [ ] **Step 1: Install the server extra in the image**

In `Dockerfile`, change the install line so the container has the full server stack:
```dockerfile
RUN pip install --no-cache-dir -e ".[server]" && chmod +x docker-entrypoint.sh
```
(The `CMD` uvicorn line and entrypoint are unchanged.)

- [ ] **Step 2: Point the scheduler service at mailbender-server**

In `docker-compose.yml`, change the scheduler service command:
```yaml
    command: ["mailbender-server", "scheduler"]
```

- [ ] **Step 3: Validate the compose file**

Run: `cp .env.example .env && docker compose config >/dev/null && echo OK; rm -f .env`
Expected: `OK`

- [ ] **Step 4: Rewrite the README CLI section**

In `README.md`, replace the `## CLI` section with a thin-client workflow and demote the container exec to an admin note:
```markdown
## CLI (thin client)

Install on your machine (no server stack required):

```bash
uv tool install mailbender      # or: pipx install mailbender
mailbender login                # prompts for API URL + token; writes ~/.config/mailbender/config.toml (chmod 600)
```

Resolution order for URL/token is **flag > env (`MAILBENDER_API_URL` / `MAILBENDER_API_TOKEN`) > config file**.

```bash
mailbender status                          # resolved url, whether a token is set, reachability
mailbender chat "What did Sarah say?"
mailbender run --type main|style|feedback   # default main
mailbender priorities
mailbender history --limit 50
mailbender audit --limit 50
mailbender categories list|add NAME|remove NAME|seed
mailbender mappings list|add CATEGORY FOLDER|remove CATEGORY
mailbender logout
```

Add `--json` to any command for machine-readable output (JSON to stdout). `--url`/`--token` override config; `--verbose` shows tracebacks.

### Server administration

Server-only operations run inside the container (full stack via the `[server]` extra):

```bash
docker compose exec scheduler mailbender-server scheduler   # the periodic loop (already the scheduler service)
```
Migrations run automatically from the container entrypoint.
```

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml README.md
git commit -m "build: install server extra in image; route scheduler to mailbender-server; doc the thin cli"
```

---

## Task 12: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full suite**

Run: `pytest -q`
Expected: PASS — api (incl. new category/run_type endpoints), client (config/api/render), thin cli, import boundary, server_cli, and the existing server-side suite all green.

- [ ] **Step 2: Verify both images build**

Run: `docker compose build`
Expected: build succeeds for `app` and `scheduler`.

- [ ] **Step 3: Smoke-check both CLIs**

```bash
mailbender --help        # thin client: login/logout/status/version/chat/run/priorities/history/audit/categories/mappings; NO scheduler
mailbender-server --help # scheduler
```
Expected: `scheduler` appears only under `mailbender-server`; the thin `mailbender` lists the client commands and command groups.

- [ ] **Step 4: Commit (if any verification fixes were needed)**

```bash
git add -A
git commit -m "chore: cli-thin-client milestone verification"
```

---

## Self-Review Notes

- **Spec coverage:**
  - Packaging & entrypoints (two scripts, base/[server] split, module boundary) → Tasks 6, 7, 9, 10, 11.
  - Config/login/HTTP client (resolve flag>env>file, login wizard + verify + chmod 600, logout, status, httpx wrapper + error translation) → Tasks 3, 4, 7.
  - Command surface & output (noun-grouped sub-apps, global `--json`, Rich tables, colored priorities, chat panel, scheduler removed from this CLI) → Tasks 5, 7, 8.
  - API extensions (POST/DELETE/seed categories, run_type on /run, 404/422, audited) → Tasks 1, 2.
  - Server-CLI, Docker, docs → Tasks 6, 10, 11.
  - Test strategy (MockTransport client tests, resolver order, import boundary, new endpoint tests, retire thick-CLI tests) → Tasks 1–9.
  - Excluded (standalone binary/Homebrew, web frontend, more server-CLI ops, scheduler run_type) → not in plan, intentional.
- **Type consistency:** `ClientConfig(url, token)`, `resolve_config(flag_url, flag_token, env, path)`, `save_config(cfg, path)`, `delete_config(path)`, `config_path()` (T3) are consumed identically by the CLI (T7) and tests. `ApiClient(config, *, transport, timeout)` with methods `health/chat/run/priorities/history/audit/categories_{list,add,remove,seed}/mappings_{list,add,remove}` (T4) match the CLI command calls (T8) and the API routes (T1, T2). `render.{emit_json,error,confirm,table,priorities,history,audit,categories,mappings,chat}` (T5) match the CLI calls (T7, T8). `_client_factory(cfg)` and `_api(ctx, fn)` (T7) are the single seams tests monkeypatch (T7, T8). `routes.run(runner, run_type)` + `routes.RUN_TYPES` (T2) and `routes.add_category/remove_category/seed_categories` (T1) match their endpoint callers.
- **M3 reconciliation:** category mutation audit now lives in the API endpoints (actor `web`, T1), consistent with M3's audit design now that the thin CLI has no DB session; the thin CLI writes no audit. The M3 `POST /run` audit test stays valid (default `run_type="main"`), with only its response-body assertion updated if present (T2 Step 4).
