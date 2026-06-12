import pytest
from mailagent.store.models import Base
from mailagent.store.repository import Repository
from mailagent.categories import DEFAULT_CATEGORIES, seed_default_categories


@pytest.fixture
def repo(db_engine, db_session):
    Base.metadata.create_all(db_engine)
    return Repository(db_session)


def test_default_categories_include_reply_category():
    names = [name for name, _desc in DEFAULT_CATEGORIES]
    assert "Antwort nötig" in names


def test_seed_adds_all_defaults(repo):
    added = seed_default_categories(repo)
    assert added == len(DEFAULT_CATEGORIES)
    names = {c.name for c in repo.list_categories()}
    assert names == {name for name, _desc in DEFAULT_CATEGORIES}


def test_seed_is_idempotent(repo):
    seed_default_categories(repo)
    added_second = seed_default_categories(repo)
    assert added_second == 0
    assert len(repo.list_categories()) == len(DEFAULT_CATEGORIES)
