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


def test_conversation_and_messages_persist(db_session):
    from mailbender.store.models import Conversation, ChatMessage
    conv = Conversation(title="Budget thread")
    db_session.add(conv)
    db_session.flush()
    db_session.add(ChatMessage(conversation_id=conv.id, role="user", text="hi"))
    db_session.add(ChatMessage(conversation_id=conv.id, role="assistant",
                               text="hello", sources_json='[{"uid":"1"}]'))
    db_session.flush()
    from sqlalchemy import select
    msgs = db_session.execute(
        select(ChatMessage).where(ChatMessage.conversation_id == conv.id)
        .order_by(ChatMessage.id)).scalars().all()
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].sources_json == '[{"uid":"1"}]'
