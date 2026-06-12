from datetime import datetime, timedelta
from mailbender.web.operator import group_by_priority, next_run_countdown


def test_group_by_priority_orders_and_counts():
    class P:
        def __init__(self, uid, pr, cat):
            self.uid = uid; self.priority = pr; self.category = cat
    rows = [P("1", "low", "Dev"), P("2", "high", "Finance"),
            P("3", "high", "Legal"), P("4", "medium", "News")]
    groups = group_by_priority(rows)
    assert [g["priority"] for g in groups] == ["high", "medium", "low"]
    assert groups[0]["count"] == 2
    assert [r.uid for r in groups[0]["rows"]] == ["2", "3"]


def test_next_run_countdown_future():
    last = datetime(2026, 6, 12, 9, 0, 0)
    now = datetime(2026, 6, 12, 9, 5, 0)
    assert next_run_countdown(last, 15, now=now) == "in 10m"


def test_next_run_countdown_overdue_and_disabled_and_never():
    last = datetime(2026, 6, 12, 9, 0, 0)
    now = datetime(2026, 6, 12, 9, 30, 0)
    assert next_run_countdown(last, 15, now=now) == "due now"
    assert next_run_countdown(last, 0, now=now) == "manual"
    assert next_run_countdown(None, 15, now=now) == "—"


from fastapi import FastAPI
from fastapi.testclient import TestClient
from mailbender.web.mount import mount_web
from mailbender.web.security import WebSecurity


class P:
    def __init__(self, uid, pr, cat):
        self.uid = uid; self.priority = pr; self.category = cat


class RunRow:
    run_type = "main"; step = "run"; result = "success"
    created_at = datetime(2026, 6, 12, 9, 0, 0); uid = None; detail = ""


class OpRepo:
    session = object()
    def processed_by_priority(self):
        return [P("1", "high", "Finance"), P("2", "low", "Dev")]
    def last_run_at(self, run_type):
        return RunRow.created_at
    def count_processed(self):
        return 2
    def list_conversations(self):
        return []


def op_client():
    app = FastAPI()
    app.state.web_security = WebSecurity(secret_key="k" * 32, password="pw")
    app.state.repo_factory = lambda: OpRepo()
    app.state.schedule_minutes = 15
    mount_web(app)
    c = TestClient(app)
    c.post("/login", data={"password": "pw"})
    return c


def test_overview_renders_status_and_groups():
    c = op_client()
    r = c.get("/app/operator")
    assert r.status_code == 200
    assert "HIGH" in r.text
    assert "Finance" in r.text
    assert "/app/operator/priorities/fragment" in r.text  # hx-poll target present


def test_priorities_page_is_full_layout():
    c = op_client()
    r = c.get("/app/operator/priorities")
    assert r.status_code == 200
    assert "Finance" in r.text
    # full page, not a bare fragment: it carries the shell (stylesheet + nav)
    assert "/static/app.css" in r.text
    assert "audit log" in r.text  # sidebar nav present


def test_priorities_fragment_is_bare():
    c = op_client()
    r = c.get("/app/operator/priorities/fragment")
    assert r.status_code == 200
    assert "Finance" in r.text
    # bare HTMX fragment: no full-page shell
    assert "/static/app.css" not in r.text
    assert 'id="priorities"' in r.text


def test_run_trigger_dispatches_and_audits(monkeypatch):
    import re
    import mailbender.web.operator_routes as opmod
    recorded = []

    class FakeAuditor:
        def __init__(self, session): pass
        def record(self, actor, action, target="", result="success"):
            recorded.append((actor, action, target))
    monkeypatch.setattr(opmod, "AuditLogger", FakeAuditor)

    class FakeRunner:
        def __init__(self): self.calls = []
        def run_main(self): self.calls.append("main")
        def run_style(self): self.calls.append("style")
        def run_feedback(self): self.calls.append("feedback")
    runner = FakeRunner()

    app = FastAPI()
    app.state.web_security = WebSecurity(secret_key="k" * 32, password="pw")
    app.state.repo_factory = lambda: OpRepo()
    app.state.runner_factory = lambda: runner
    app.state.schedule_minutes = 15
    mount_web(app)
    c = TestClient(app)
    c.post("/login", data={"password": "pw"})
    token = re.search(r'name="csrf_token" value="([^"]+)"',
                      c.get("/app/operator").text).group(1)

    # success -> 204, dispatched, audited
    r = c.post("/app/operator/run", data={"run_type": "style", "csrf_token": token})
    assert r.status_code == 204
    assert runner.calls == ["style"]
    assert ("web", "run_triggered", "style") in recorded

    # invalid run_type -> 422
    assert c.post("/app/operator/run",
                  data={"run_type": "nope", "csrf_token": token}).status_code == 422

    # missing csrf -> 403
    assert c.post("/app/operator/run", data={"run_type": "main"}).status_code == 403
