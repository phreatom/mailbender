import pytest
from mailagent.store.models import Base
from mailagent.store.repository import Repository
from mailagent.llm.fake import FakeLLMProvider
from mailagent.llm.provider import Email
from mailagent.scheduler.runner import Runner


class FakeImap:
    def __init__(self, inbox):
        self._inbox = inbox
        self.moved = []
        self.drafts = []
        self.drafts_folder = "Drafts"
        self.sent_folder = "Sent"

    def fetch_inbox(self):
        return self._inbox

    def append_draft(self, subject, body, folder=None):
        self.drafts.append((subject, body))

    def move(self, uid, target_folder, source_folder="INBOX"):
        self.moved.append((uid, target_folder))


@pytest.fixture
def session(db_engine, db_session):
    Base.metadata.create_all(db_engine)
    return db_session


def test_main_run_classifies_and_drafts_for_reply_needed(session):
    inbox = [Email(uid="1", subject="Frage", sender="a@b.c", body="?",
                   message_id="<m1>")]
    imap = FakeImap(inbox)
    provider = FakeLLMProvider(category="Antwort nötig", priority="high",
                               draft="Hallo!")
    runner = Runner(
        imap=imap, provider=provider, session=session,
        categories=["Antwort nötig", "Newsletter"],
        mapping={}, reply_category="Antwort nötig",
        style_examples=["Grüße"],
    )
    runner.run_main()
    assert Repository(session).is_processed("1")
    assert imap.drafts == [("Re: Frage", "Hallo!")]


def test_main_run_skips_already_processed(session):
    Repository(session).mark_processed("1", "X", "low", False, False)
    inbox = [Email(uid="1", subject="x", sender="a@b.c", body="b")]
    imap = FakeImap(inbox)
    runner = Runner(
        imap=imap, provider=FakeLLMProvider(), session=session,
        categories=["X"], mapping={}, reply_category="Antwort nötig",
        style_examples=[],
    )
    runner.run_main()
    assert imap.drafts == []


def test_main_run_records_history_steps(session):
    from sqlalchemy import select
    from mailagent.store.models import RunHistory
    inbox = [Email(uid="1", subject="Frage", sender="a@b.c", body="?",
                   message_id="<m1>")]
    imap = FakeImap(inbox)
    provider = FakeLLMProvider(category="Antwort nötig", priority="high",
                               draft="Hallo!")
    runner = Runner(
        imap=imap, provider=provider, session=session,
        categories=["Antwort nötig"], mapping={},
        reply_category="Antwort nötig", style_examples=["Grüße"],
    )
    runner.run_main()
    rows = session.execute(select(RunHistory)).scalars().all()
    steps = {r.step for r in rows}
    assert {"classify", "prioritize", "index", "move", "draft", "run"} <= steps
    marker = [r for r in rows if r.step == "run"]
    assert len(marker) == 1 and marker[0].run_type == "main"
