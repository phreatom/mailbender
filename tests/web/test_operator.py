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
    assert "HIGH" in r.text.upper()
    assert "Finance" in r.text
    assert "/app/operator/priorities" in r.text  # hx-poll target present


def test_priorities_partial_pollable():
    c = op_client()
    r = c.get("/app/operator/priorities")
    assert r.status_code == 200
    assert "Finance" in r.text
