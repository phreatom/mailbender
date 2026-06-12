import pytest
from sqlalchemy import select
from mailagent.store.models import Base, AuditLog
from mailagent.audit.log import AuditLogger


@pytest.fixture
def session(db_engine, db_session):
    Base.metadata.create_all(db_engine)
    return db_session


def test_record_audit_entry(session):
    auditor = AuditLogger(session)
    auditor.record(actor="scheduler", action="draft_append",
                   target="uid-1", result="success")
    rows = session.execute(select(AuditLog)).scalars().all()
    assert len(rows) == 1
    assert rows[0].action == "draft_append"
    assert rows[0].result == "success"
