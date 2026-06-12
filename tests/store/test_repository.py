import pytest
from mailagent.store.models import Base
from mailagent.store.repository import Repository


@pytest.fixture
def repo(db_engine, db_session):
    Base.metadata.create_all(db_engine)
    return Repository(db_session)


def test_mark_and_check_processed(repo):
    assert repo.is_processed("uid-1") is False
    repo.mark_processed("uid-1", category="Newsletter", priority="low",
                        moved=True, drafted=False)
    assert repo.is_processed("uid-1") is True


def test_mark_processed_is_idempotent(repo):
    repo.mark_processed("uid-2", category="X", priority="high",
                        moved=False, drafted=False)
    repo.mark_processed("uid-2", category="X", priority="high",
                        moved=False, drafted=False)
    assert repo.count_processed() == 1


def test_add_and_list_categories(repo):
    repo.add_category("Rechnung", "Invoices and bills")
    names = [c.name for c in repo.list_categories()]
    assert "Rechnung" in names


def test_remove_category(repo):
    repo.add_category("Werbung", "Ads")
    assert "Werbung" in [c.name for c in repo.list_categories()]
    removed = repo.remove_category("Werbung")
    assert removed is True
    assert "Werbung" not in [c.name for c in repo.list_categories()]


def test_remove_missing_category_returns_false(repo):
    assert repo.remove_category("DoesNotExist") is False
