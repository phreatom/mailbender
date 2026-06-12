from fastapi import FastAPI
from fastapi.testclient import TestClient
from mailbender.web.mount import mount_web
from mailbender.web.security import WebSecurity, SESSION_COOKIE


class _EmptyRepo:
    def list_conversations(self):
        return []
    def get_conversation(self, cid):
        return None


def make_client(password="hunter2"):
    app = FastAPI()
    app.state.web_security = WebSecurity(secret_key="k" * 32, password=password)
    app.state.repo_factory = lambda: _EmptyRepo()
    mount_web(app)
    return TestClient(app)


def test_login_page_renders():
    c = make_client()
    r = c.get("/login")
    assert r.status_code == 200
    assert "password" in r.text.lower()


def test_login_rejects_wrong_password():
    c = make_client()
    r = c.post("/login", data={"password": "nope"}, follow_redirects=False)
    assert r.status_code == 200
    assert SESSION_COOKIE not in r.cookies
    assert "incorrect" in r.text.lower()


def test_login_sets_cookie_and_redirects():
    c = make_client()
    r = c.post("/login", data={"password": "hunter2"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/app"
    assert SESSION_COOKIE in r.cookies


def test_app_requires_session_redirects_to_login():
    c = make_client()
    r = c.get("/app", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_app_accessible_after_login():
    c = make_client()
    c.post("/login", data={"password": "hunter2"})
    r = c.get("/app")
    assert r.status_code == 200


def test_logout_clears_cookie():
    c = make_client()
    c.post("/login", data={"password": "hunter2"})
    r = c.get("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
    r2 = c.get("/app", follow_redirects=False)
    assert r2.status_code == 303


def test_login_disabled_when_no_password():
    c = make_client(password="")
    r = c.get("/login")
    assert "not configured" in r.text.lower()
    r2 = c.post("/login", data={"password": ""}, follow_redirects=False)
    assert SESSION_COOKIE not in r2.cookies
