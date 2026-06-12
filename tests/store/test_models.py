from mailbender.store.models import (
    Base, ProcessedMail, Category, FolderMapping, StyleExample,
    ReferenceDraft, RunHistory, AuditLog, MailIndex,
)


def test_create_all_tables(db_engine):
    Base.metadata.create_all(db_engine)
    table_names = set(Base.metadata.tables.keys())
    assert {
        "processed_mail", "category", "folder_mapping", "style_example",
        "reference_draft", "run_history", "audit_log", "mail_index",
    } <= table_names
