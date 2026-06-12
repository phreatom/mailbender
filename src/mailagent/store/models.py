from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    pass


class ProcessedMail(Base):
    __tablename__ = "processed_mail"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    category: Mapped[str | None] = mapped_column(String(100))
    priority: Mapped[str | None] = mapped_column(String(20))
    moved: Mapped[bool] = mapped_column(default=False)
    drafted: Mapped[bool] = mapped_column(default=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Category(Base):
    __tablename__ = "category"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")


class FolderMapping(Base):
    __tablename__ = "folder_mapping"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_name: Mapped[str] = mapped_column(String(100), unique=True)
    target_folder: Mapped[str] = mapped_column(String(255))


class StyleExample(Base):
    __tablename__ = "style_example"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(default=1.0)
    source: Mapped[str] = mapped_column(String(20))  # "bootstrap" | "feedback"
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ReferenceDraft(Base):
    __tablename__ = "reference_draft"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_uid: Mapped[str] = mapped_column(String(255), index=True)
    message_id: Mapped[str] = mapped_column(String(512), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RunHistory(Base):
    __tablename__ = "run_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_type: Mapped[str] = mapped_column(String(20))  # main|style|feedback
    uid: Mapped[str | None] = mapped_column(String(255))
    step: Mapped[str] = mapped_column(String(50))
    result: Mapped[str] = mapped_column(String(20))  # success|error|skipped
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(100))
    target: Mapped[str] = mapped_column(String(255), default="")
    result: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MailIndex(Base):
    __tablename__ = "mail_index"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    subject: Mapped[str] = mapped_column(Text, default="")
    sender: Mapped[str] = mapped_column(String(512), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
