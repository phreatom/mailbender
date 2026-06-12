import pytest
from mailbender.store.models import Base, ReferenceDraft
from mailbender.llm.fake import FakeLLMProvider
from mailbender.llm.provider import Email
from mailbender.pipeline.draft_generator import DraftGenerator
from sqlalchemy import select


class FakeImap:
    def __init__(self):
        self.drafts = []

    def append_draft(self, subject, body, folder=None):
        self.drafts.append((subject, body))


@pytest.fixture
def session(db_engine, db_session):
    Base.metadata.create_all(db_engine)
    return db_session


def test_generate_appends_draft_and_stores_reference(session):
    imap = FakeImap()
    gen = DraftGenerator(FakeLLMProvider(draft="Hallo, danke."), imap, session)
    email = Email(uid="1", subject="Frage", sender="a@b.c", body="?",
                  message_id="<m1>")
    gen.generate(email, style_examples=["Mit besten Grüßen"])
    assert imap.drafts == [("Re: Frage", "Hallo, danke.")]
    refs = session.execute(select(ReferenceDraft)).scalars().all()
    assert len(refs) == 1
    assert refs[0].source_uid == "1"
    assert refs[0].content == "Hallo, danke."


def test_generate_is_idempotent_for_same_uid(session):
    imap = FakeImap()
    gen = DraftGenerator(FakeLLMProvider(draft="Hallo."), imap, session)
    email = Email(uid="dup-1", subject="Frage", sender="a@b.c", body="?",
                  message_id="<m1>")
    gen.generate(email, style_examples=[])
    gen.generate(email, style_examples=[])  # second call must be a no-op
    assert len(imap.drafts) == 1
    refs = session.execute(select(ReferenceDraft)).scalars().all()
    assert len(refs) == 1
