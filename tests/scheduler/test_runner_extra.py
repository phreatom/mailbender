import pytest
from mailbender.store.models import Base, StyleExample
from mailbender.llm.fake import FakeLLMProvider
from mailbender.llm.provider import Email
from mailbender.scheduler.runner import Runner
from sqlalchemy import select


class FakeImap:
    def __init__(self, sent):
        self._sent = sent
        self.sent_folder = "Sent"
        self.drafts_folder = "Drafts"

    def fetch_inbox(self):
        return []

    def fetch_folder(self, folder):
        return self._sent


@pytest.fixture
def session(db_engine, db_session):
    Base.metadata.create_all(db_engine)
    return db_session


def test_run_style_bootstraps(session):
    sent = [Email(uid="1", subject="s", sender="me@x.c", body="Grüße")]
    runner = Runner(imap=FakeImap(sent), provider=FakeLLMProvider(),
                    session=session, categories=["X"], mapping={},
                    reply_category="Antwort nötig", style_examples=[])
    runner.run_style()
    rows = session.execute(select(StyleExample)).scalars().all()
    assert len(rows) == 1
