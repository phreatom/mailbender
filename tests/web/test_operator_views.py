from datetime import datetime
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mailbender.web.mount import mount_web
from mailbender.web.security import WebSecurity


class Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class ViewsRepo:
    def __init__(self):
        self.categories = [Row(name="Newsletter", description="news")]
        self.mappings = [Row(category_name="Newsletter", target_folder="Archive/News")]
        self.added = []
        self.removed = []
    def recent_runs(self, limit):
        return [Row(run_type="main", uid="1", step="classify", result="success",
                    detail="Finance", created_at=datetime(2026, 6, 12, 9, 0))]
    def recent_audit(self, limit):
        return [Row(actor="web", action="run_triggered", target="main",
                    result="success", created_at=datetime(2026, 6, 12, 9, 0))]
    def list_categories(self):
        return self.categories
    def list_mappings(self):
        return self.mappings
    def list_conversations(self):
        return []
    session = object()
    def add_category(self, name, description=""):
        self.added.append(("cat", name))
    def remove_category(self, name):
        self.removed.append(("cat", name)); return True
    def add_mapping(self, c, f):
        self.added.append(("map", c, f))
    def remove_mapping(self, c):
        self.removed.append(("map", c)); return True


def client_and_repo(monkeypatch):
    import mailbender.web.operator_routes as opmod

    class FakeAuditor:
        def __init__(self, session): pass
        def record(self, *a, **k): pass
    monkeypatch.setattr(opmod, "AuditLogger", FakeAuditor)
    app = FastAPI()
    app.state.web_security = WebSecurity(secret_key="k" * 32, password="pw")
    repo = ViewsRepo()
    app.state.repo_factory = lambda: repo
    mount_web(app)
    c = TestClient(app)
    c.post("/login", data={"password": "pw"})
    return c, repo


def _csrf(c):
    import re
    m = re.search(r'name="csrf_token" value="([^"]+)"',
                  c.get("/app/operator/categories").text)
    return m.group(1)


def test_runs_and_audit_render(monkeypatch):
    c, _ = client_and_repo(monkeypatch)
    assert "classify" in c.get("/app/operator/runs").text
    assert "run_triggered" in c.get("/app/operator/audit").text


def test_categories_add_remove(monkeypatch):
    c, repo = client_and_repo(monkeypatch)
    token = _csrf(c)
    c.post("/app/operator/categories/add",
           data={"name": "Finance", "description": "money", "csrf_token": token})
    assert ("cat", "Finance") in repo.added
    c.post("/app/operator/categories/remove",
           data={"name": "Finance", "csrf_token": token})
    assert ("cat", "Finance") in repo.removed


def test_mappings_add_remove(monkeypatch):
    c, repo = client_and_repo(monkeypatch)
    token = _csrf(c)
    c.post("/app/operator/mappings/add",
           data={"category": "Finance", "folder": "Archive/Fin", "csrf_token": token})
    assert ("map", "Finance", "Archive/Fin") in repo.added
    c.post("/app/operator/mappings/remove",
           data={"category": "Finance", "csrf_token": token})
    assert ("map", "Finance") in repo.removed


def test_category_add_rejected_without_csrf(monkeypatch):
    c, repo = client_and_repo(monkeypatch)
    r = c.post("/app/operator/categories/add", data={"name": "X"})
    assert r.status_code == 403
