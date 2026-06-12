import pytest
from sqlalchemy import select
from mailagent.store.models import Base, StyleExample
from mailagent.llm.provider import Email
from mailagent.learning.style_learner import StyleLearner


class FakeImap:
    def __init__(self, sent):
        self._sent = sent
        self.sent_folder = "Sent"

    def fetch_folder(self, folder):
        return self._sent


@pytest.fixture
def session(db_engine, db_session):
    Base.metadata.create_all(db_engine)
    return db_session


def test_bootstrap_stores_examples(session):
    sent = [Email(uid="1", subject="s", sender="me@x.c", body="Mit besten Grüßen, Tom")]
    learner = StyleLearner(FakeImap(sent), session, sample_size=10)
    count = learner.bootstrap()
    assert count == 1
    rows = session.execute(select(StyleExample)).scalars().all()
    assert rows[0].source == "bootstrap"
    assert "Grüßen" in rows[0].content


def test_get_style_examples_returns_content(session):
    session.add(StyleExample(content="Beispiel", source="bootstrap", weight=1.0))
    session.commit()
    learner = StyleLearner(FakeImap([]), session, sample_size=10)
    examples = learner.get_style_examples(limit=5)
    assert examples == ["Beispiel"]
