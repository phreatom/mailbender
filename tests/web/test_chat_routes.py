from fastapi import FastAPI
from fastapi.testclient import TestClient
from mailbender.web.mount import mount_web
from mailbender.web.security import WebSecurity
from mailbender.chat.chat import ChatAnswer, ChatSource


class FakeConv:
    def __init__(self, id, title, messages=None):
        self.id = id; self.title = title; self.messages = messages or []


class FakeMsg:
    def __init__(self, role, text, sources_json="[]"):
        self.role = role; self.text = text; self.sources_json = sources_json


class FakeRepo:
    def __init__(self):
        self.convs = {}
        self.appended = []

    def list_conversations(self):
        return list(self.convs.values())

    def create_conversation(self, title):
        c = FakeConv(len(self.convs) + 1, title)
        self.convs[c.id] = c
        return c

    def get_conversation(self, cid):
        return self.convs.get(cid)

    def append_message(self, cid, role, text, sources):
        self.convs[cid].messages.append(FakeMsg(role, text))
        self.appended.append((cid, role, text, tuple(s["uid"] for s in sources)))


class FakeChat:
    class provider:  # for the provider_use audit line
        pass

    def ask(self, question, history=None):
        self.history = history
        return ChatAnswer(text="ANSWER", sources=[ChatSource(uid="9", subject="S")])


def make():
    app = FastAPI()
    app.state.web_security = WebSecurity(secret_key="k" * 32, password="pw")
    repo = FakeRepo()
    chat = FakeChat()
    app.state.repo_factory = lambda: repo
    app.state.chat_factory = lambda: chat
    mount_web(app)
    c = TestClient(app)
    c.post("/login", data={"password": "pw"})
    return c, repo, chat


def _csrf(client):
    page = client.get("/app")
    import re
    m = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert m, "csrf token not found on page"
    return m.group(1)


def test_chat_page_requires_auth():
    app = FastAPI()
    app.state.web_security = WebSecurity(secret_key="k" * 32, password="pw")
    app.state.repo_factory = lambda: FakeRepo()
    mount_web(app)
    r = TestClient(app).get("/app", follow_redirects=False)
    assert r.status_code == 303


def test_new_conversation_then_message_threads_history():
    c, repo, chat = make()
    new = c.post("/app/chat/new", data={"csrf_token": _csrf(c)}, follow_redirects=False)
    assert new.status_code == 303
    cid = list(repo.convs)[0]
    repo.convs[cid].messages.append(FakeMsg("user", "earlier"))
    repo.convs[cid].messages.append(FakeMsg("assistant", "prior"))
    r = c.post(f"/app/chat/{cid}/message",
               data={"question": "now?", "csrf_token": _csrf(c)})
    assert r.status_code == 200
    assert "ANSWER" in r.text
    roles = [a[1] for a in repo.appended]
    assert roles == ["user", "assistant"]
    assert ("user", "earlier") in chat.history


def test_message_rejected_without_csrf():
    c, repo, chat = make()
    c.post("/app/chat/new", data={"csrf_token": _csrf(c)})
    cid = list(repo.convs)[0]
    r = c.post(f"/app/chat/{cid}/message", data={"question": "x"})
    assert r.status_code == 403


def test_new_conversation_rejected_without_csrf():
    c, repo, chat = make()
    r = c.post("/app/chat/new", follow_redirects=False)
    assert r.status_code == 403
