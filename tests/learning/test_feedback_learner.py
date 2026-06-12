import pytest
from sqlalchemy import select
from mailbender.store.models import Base, ReferenceDraft, StyleExample
from mailbender.llm.provider import Email
from mailbender.learning.feedback_learner import FeedbackLearner


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


def test_matched_sent_creates_weighted_example(session):
    session.add(ReferenceDraft(source_uid="1", message_id="<m1>",
                               content="Hallo, danke."))
    session.commit()
    sent = [Email(uid="9", subject="Re: x", sender="me@x.c",
                  body="Hallo, vielen herzlichen Dank!",
                  in_reply_to="<m1>")]
    learner = FeedbackLearner(FakeImap(sent), session)
    matched = learner.run()
    assert matched == 1
    examples = session.execute(
        select(StyleExample).where(StyleExample.source == "feedback")
    ).scalars().all()
    assert len(examples) == 1
    assert examples[0].content == "Hallo, vielen herzlichen Dank!"
    assert examples[0].weight > 1.0  # edited draft -> higher weight


def test_no_match_is_skipped(session):
    sent = [Email(uid="9", subject="Re: x", sender="me@x.c",
                  body="text", in_reply_to="<unknown>")]
    learner = FeedbackLearner(FakeImap(sent), session)
    assert learner.run() == 0
