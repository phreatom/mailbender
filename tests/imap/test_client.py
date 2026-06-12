import smtplib
import time
from email.message import EmailMessage
import pytest
from mailbender.imap.client import ImapClient


def _send(subject, body):
    msg = EmailMessage()
    msg["From"] = "sender@example.com"
    msg["To"] = "me@example.com"
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP("localhost", 53025) as s:
        s.send_message(msg)


@pytest.fixture
def imap(docker_services):
    docker_services.wait_until_responsive(
        timeout=60.0, pause=1.0, check=lambda: ImapClient.can_connect(
            "localhost", 53143, "me", "secret"))
    return ImapClient(host="localhost", port=53143, user="me",
                      password="secret", use_ssl=False)


def test_fetch_new_messages(imap):
    _send("Hello", "world")
    time.sleep(1)
    emails = imap.fetch_inbox()
    assert any(e.subject == "Hello" for e in emails)


def test_append_draft(imap):
    imap.append_draft("Draft subject", "Draft body", folder="INBOX")
    emails = imap.fetch_folder("INBOX")
    assert any(e.subject == "Draft subject" for e in emails)


def test_connect_retries_transient_failure(monkeypatch):
    import mailbender.imap.client as mod

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
