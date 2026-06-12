from fastapi.testclient import TestClient
from mailagent.api.app import create_app


def test_health_no_auth_required():
    client = TestClient(create_app(api_token="secret-token"))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_categories_requires_auth():
    client = TestClient(create_app(api_token="secret-token"))
    resp = client.get("/categories")
    assert resp.status_code == 401


def test_categories_with_valid_token():
    app = create_app(api_token="secret-token")

    class FakeRepo:
        def list_categories(self):
            class C:
                name = "Newsletter"
            return [C()]

    app.state.repo_factory = lambda: FakeRepo()
    client = TestClient(app)
    resp = client.get("/categories",
                      headers={"Authorization": "Bearer secret-token"})
    assert resp.status_code == 200
    assert resp.json() == ["Newsletter"]


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


def test_all_protected_endpoints_require_auth():
    client = TestClient(create_app(api_token="t"))
    assert client.get("/categories").status_code == 401
    assert client.post("/run").status_code == 401
    assert client.get("/priorities").status_code == 401
    assert client.get("/history").status_code == 401
    assert client.get("/audit").status_code == 401
    assert client.get("/mappings").status_code == 401
    assert client.post("/mappings", json={"category": "N", "folder": "F"}).status_code == 401
    assert client.request("DELETE", "/mappings/N").status_code == 401
    # /health stays public
    assert client.get("/health").status_code == 200
