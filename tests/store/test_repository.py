import pytest
from mailbender.store.models import Base
from mailbender.store.repository import Repository


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


def test_record_and_query_run_history(repo):
    repo.record_run_step("main", "uid-1", "classify", "success", "Newsletter")
    repo.record_run_step("main", None, "run", "success")
    runs = repo.recent_runs(limit=10)
    assert len(runs) == 2
    assert {r.step for r in runs} == {"classify", "run"}


def test_last_run_at_returns_none_then_timestamp(repo):
    assert repo.last_run_at("main") is None
    repo.record_run_step("main", None, "run", "success")
    assert repo.last_run_at("main") is not None
    assert repo.last_run_at("feedback") is None


def test_recent_audit_returns_entries(repo):
    from mailbender.audit.log import AuditLogger
    AuditLogger(repo.session).record("scheduler", "draft_append", "uid-1")
    rows = repo.recent_audit(limit=10)
    assert len(rows) == 1
    assert rows[0].action == "draft_append"


def test_processed_by_priority_orders_high_first(repo):
    repo.mark_processed("a", "X", "low", False, False)
    repo.mark_processed("b", "X", "high", False, False)
    repo.mark_processed("c", "X", "medium", False, False)
    order = [p.priority for p in repo.processed_by_priority()]
    assert order == ["high", "medium", "low"]


def test_add_list_remove_mapping(repo):
    repo.add_mapping("Newsletter", "Archive/News")
    mappings = {m.category_name: m.target_folder for m in repo.list_mappings()}
    assert mappings == {"Newsletter": "Archive/News"}
    assert repo.remove_mapping("Newsletter") is True
    assert repo.list_mappings() == []
    assert repo.remove_mapping("Newsletter") is False


def test_add_mapping_upserts_target(repo):
    repo.add_mapping("Newsletter", "Archive/News")
    repo.add_mapping("Newsletter", "Archive/Old")
    mappings = {m.category_name: m.target_folder for m in repo.list_mappings()}
    assert mappings == {"Newsletter": "Archive/Old"}
