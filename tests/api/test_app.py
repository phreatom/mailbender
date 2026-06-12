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
