import pytest
from mailagent.store.models import Base, MailIndex
from mailagent.llm.fake import FakeLLMProvider
from mailagent.chat.chat import Chat


@pytest.fixture
def session(db_engine, db_session):
    Base.metadata.create_all(db_engine)
    return db_session


def _add_mail(session, uid, body, vec):
    session.add(MailIndex(uid=uid, subject="s", sender="sarah@x.c",
                          body=body, embedding=vec))
    session.commit()


def test_chat_returns_answer_with_context(session):
    _add_mail(session, "1", "Sarah approved the Q4 budget", [0.1] * 1536)
    provider = FakeLLMProvider(chat_answer="Sarah approved it.")
    chat = Chat(provider, session)
    answer = chat.ask("What did Sarah say about the budget?")
    assert "Sarah" in answer.text
    assert "1" in [s.uid for s in answer.sources]


def test_chat_empty_index_returns_no_info(session):
    chat = Chat(FakeLLMProvider(), session)
    answer = chat.ask("anything?")
    assert "Keine passende Information" in answer.text
    assert answer.sources == []
