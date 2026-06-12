import pytest
from sqlalchemy import select
from mailbender.store.models import Base, MailIndex
from mailbender.llm.fake import FakeLLMProvider
from mailbender.llm.provider import Email
from mailbender.pipeline.indexer import Indexer


@pytest.fixture
def session(db_engine, db_session):
    Base.metadata.create_all(db_engine)
    return db_session


def test_index_stores_embedding(session):
    idx = Indexer(FakeLLMProvider(), session)
    email = Email(uid="1", subject="Budget", sender="sarah@x.c", body="approved")
    idx.index(email)
    rows = session.execute(select(MailIndex)).scalars().all()
    assert len(rows) == 1
    assert rows[0].uid == "1"
    assert len(rows[0].embedding) == 1536


def test_index_is_idempotent(session):
    idx = Indexer(FakeLLMProvider(), session)
    email = Email(uid="2", subject="s", sender="a@b.c", body="b")
    idx.index(email)
    idx.index(email)
    rows = session.execute(select(MailIndex)).scalars().all()
    assert len(rows) == 1
