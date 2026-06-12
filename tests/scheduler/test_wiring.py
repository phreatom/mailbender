import pytest
from mailagent.store.models import Base, FolderMapping, StyleExample
from mailagent.store.repository import Repository
from mailagent.llm.fake import FakeLLMProvider
from mailagent.scheduler.wiring import build_runner


class FakeImap:
    def __init__(self):
        self.sent_folder = "Sent"
        self.drafts_folder = "Drafts"


@pytest.fixture
def session(db_engine, db_session):
    Base.metadata.create_all(db_engine)
    return db_session


def test_build_runner_loads_categories_mapping_and_style(session):
    repo = Repository(session)
    repo.add_category("Antwort nötig", "")
    repo.add_category("Newsletter", "")
    session.add(FolderMapping(category_name="Newsletter", target_folder="Archive/News"))
    session.add(StyleExample(content="Mit besten Grüßen", source="bootstrap", weight=2.0))
    session.commit()

    runner = build_runner(session, FakeImap(), FakeLLMProvider())

    assert set(runner.categories) == {"Antwort nötig", "Newsletter"}
    assert runner.mover.mapping == {"Newsletter": "Archive/News"}
    assert runner.reply_category == "Antwort nötig"
    assert runner.style_examples == ["Mit besten Grüßen"]


def test_build_runner_respects_reply_category_override(session):
    Base.metadata.create_all(session.get_bind())
    runner = build_runner(session, FakeImap(), FakeLLMProvider(),
                          reply_category="Custom")
    assert runner.reply_category == "Custom"
