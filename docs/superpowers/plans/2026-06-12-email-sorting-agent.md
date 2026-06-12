# E-Mail-Sortier- und Antwort-Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-hosted service that classifies, prioritizes, and indexes IMAP emails, auto-generates reply drafts in the user's learned writing style, and answers questions about the mailbox via AI chat — exposed through both a CLI and a web API.

**Architecture:** A modular monolith in Python. A shared `core` package holds all business modules (imap-client, classifier, prioritizer, draft-generator, style/feedback-learner, mover, chat, scheduler, store). Two thin frontends (Typer CLI, FastAPI web API) call into `core`. PostgreSQL (with the pgvector extension) is the single store, accessed via SQLAlchemy + Alembic migrations. The LLM provider is abstracted behind one interface with a fake implementation for tests. Deployed as two containers (app + postgres) via docker-compose.

**Tech Stack:** Python 3.12, FastAPI, Typer, SQLAlchemy 2.x, Alembic, psycopg, pgvector, IMAPClient, pytest, pytest-docker (Greenmail/Dovecot + Postgres test containers), ruff.

---

## File Structure

```
pyproject.toml                      # project metadata, deps, tool config
docker-compose.yml                  # app + postgres (pgvector) services
Dockerfile                          # app image
alembic.ini                         # migration config
migrations/                         # alembic migration scripts
src/mailagent/
  __init__.py
  config.py                         # load config from ENV/file (creds, provider, schedule)
  llm/
    __init__.py
    provider.py                     # LLMProvider protocol: classify/prioritize/generate_draft/embed/chat
    fake.py                         # FakeLLMProvider for deterministic tests
    openai_provider.py              # cloud default implementation
  store/
    __init__.py
    db.py                           # engine/session factory
    models.py                       # SQLAlchemy ORM models
    repository.py                   # CRUD + idempotency helpers
  imap/
    __init__.py
    client.py                       # ImapClient: fetch/move/append-draft/read-sent
  pipeline/
    __init__.py
    classifier.py                   # Mail -> category
    prioritizer.py                  # Mail -> urgency level
    mover.py                        # category -> folder mapping + move
    draft_generator.py              # generate + append draft, store reference draft
    indexer.py                      # embed + store mail content for chat
  learning/
    __init__.py
    style_learner.py                # bootstrap style profile from Sent
    feedback_learner.py             # draft<->sent diff -> update style profile
  chat/
    __init__.py
    chat.py                         # retrieval over embeddings + answer
  scheduler/
    __init__.py
    runner.py                       # main run, style run, feedback run
  audit/
    __init__.py
    log.py                          # append-only audit log writer
  api/
    __init__.py
    app.py                          # FastAPI app + auth
    routes.py                       # endpoints
  cli/
    __init__.py
    main.py                         # Typer app
tests/
  conftest.py                       # postgres + imap test fixtures, fake provider
  ...                               # mirrors src structure
```

Each module has one responsibility. `core` modules never import from `api`/`cli`. Tests mirror the source tree.

---

## Task 1: Project scaffold and tooling

**Files:**
- Create: `pyproject.toml`
- Create: `src/mailagent/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Write the failing test**

`tests/test_smoke.py`:
```python
def test_package_imports():
    import mailagent
    assert mailagent.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_smoke.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent'`

- [ ] **Step 3: Create pyproject.toml and package**

`pyproject.toml`:
```toml
[project]
name = "mailagent"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "typer>=0.12",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "psycopg[binary]>=3.1",
    "pgvector>=0.2.5",
    "imapclient>=3.0",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-docker>=3.1", "ruff>=0.4"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]

[project.scripts]
mailagent = "mailagent.cli.main:app"
```

`src/mailagent/__init__.py`:
```python
__version__ = "0.1.0"
```

`tests/__init__.py`: (empty file)

- [ ] **Step 4: Install and run test to verify it passes**

Run: `pip install -e ".[dev]" && pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/mailagent/__init__.py tests/__init__.py tests/test_smoke.py
git commit -m "chore: scaffold mailagent python package"
```

---

## Task 2: Configuration loading

**Files:**
- Create: `src/mailagent/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
import os
from mailagent.config import load_config


def test_load_config_from_env(monkeypatch):
    monkeypatch.setenv("MAILAGENT_DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("MAILAGENT_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("MAILAGENT_IMAP_USER", "me@example.com")
    monkeypatch.setenv("MAILAGENT_IMAP_PASSWORD", "secret")
    monkeypatch.setenv("MAILAGENT_LLM_PROVIDER", "fake")
    cfg = load_config()
    assert cfg.database_url == "postgresql+psycopg://u:p@localhost/db"
    assert cfg.imap.host == "imap.example.com"
    assert cfg.imap.user == "me@example.com"
    assert cfg.imap.password.get_secret_value() == "secret"
    assert cfg.llm_provider == "fake"


def test_defaults(monkeypatch):
    monkeypatch.setenv("MAILAGENT_DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("MAILAGENT_IMAP_HOST", "h")
    monkeypatch.setenv("MAILAGENT_IMAP_USER", "u")
    monkeypatch.setenv("MAILAGENT_IMAP_PASSWORD", "p")
    cfg = load_config()
    assert cfg.llm_provider == "openai"
    assert cfg.imap.port == 993
    assert cfg.schedule_minutes == 15
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.config'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/config.py`:
```python
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ImapConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MAILAGENT_IMAP_")
    host: str
    user: str
    password: SecretStr
    port: int = 993
    drafts_folder: str = "Drafts"
    sent_folder: str = "Sent"


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MAILAGENT_")
    database_url: str
    llm_provider: str = "openai"
    llm_api_key: SecretStr | None = None
    schedule_minutes: int = 15
    imap: ImapConfig | None = None


def load_config() -> Config:
    cfg = Config()
    if cfg.imap is None:
        cfg.imap = ImapConfig()
    return cfg
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/config.py tests/test_config.py
git commit -m "feat: add configuration loading from env"
```

---

## Task 3: Postgres test fixture and DB engine

**Files:**
- Create: `tests/conftest.py`
- Create: `src/mailagent/store/__init__.py`
- Create: `src/mailagent/store/db.py`
- Test: `tests/store/test_db.py`
- Create: `tests/store/__init__.py`

- [ ] **Step 1: Write the failing test**

`tests/store/test_db.py`:
```python
from sqlalchemy import text


def test_engine_connects(db_session):
    result = db_session.execute(text("SELECT 1")).scalar()
    assert result == 1
```

`tests/conftest.py`:
```python
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

POSTGRES_URL = "postgresql+psycopg://postgres:postgres@localhost:55432/mailagent_test"


@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig):
    return str(pytestconfig.rootdir / "tests" / "docker-compose.test.yml")


@pytest.fixture(scope="session")
def db_engine(docker_services):
    docker_services.wait_until_responsive(
        timeout=60.0, pause=1.0, check=lambda: _can_connect(POSTGRES_URL)
    )
    engine = create_engine(POSTGRES_URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    return engine


def _can_connect(url: str) -> bool:
    try:
        create_engine(url).connect().close()
        return True
    except Exception:
        return False


@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()
```

`tests/docker-compose.test.yml`:
```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: mailagent_test
    ports:
      - "55432:5432"
```

`tests/store/__init__.py`: (empty file)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_db.py -v`
Expected: FAIL — `db_session` works via conftest, but assert/import may fail because `mailagent.store.db` is unused here; this test only validates the fixture. If the fixture is missing pytest-docker plugin, install it. Expected first failure: connection/plugin error.

- [ ] **Step 3: Write the implementation**

`src/mailagent/store/__init__.py`: (empty file)

`src/mailagent/store/db.py`:
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session


def make_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True)


def make_session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)


def session_scope(session_factory) -> Session:
    return session_factory()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/store/test_db.py -v`
Expected: PASS (Postgres test container starts, `SELECT 1` returns 1)

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/docker-compose.test.yml src/mailagent/store tests/store
git commit -m "test: add postgres+pgvector test fixture and db engine"
```

---

## Task 4: ORM models and Alembic migration

**Files:**
- Create: `src/mailagent/store/models.py`
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/versions/0001_initial.py`
- Test: `tests/store/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/store/test_models.py`:
```python
from mailagent.store.models import (
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.store.models'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/store/models.py`:
```python
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
```

`alembic.ini` (minimal):
```ini
[alembic]
script_location = migrations
sqlalchemy.url = postgresql+psycopg://postgres:postgres@localhost:5432/mailagent
```

`migrations/env.py`:
```python
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from mailagent.store.models import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
```

`migrations/versions/0001_initial.py`:
```python
"""initial schema"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    from mailagent.store.models import Base
    Base.metadata.create_all(op.get_bind())


def downgrade():
    from mailagent.store.models import Base
    Base.metadata.drop_all(op.get_bind())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/store/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/store/models.py alembic.ini migrations
git commit -m "feat: add ORM models and initial migration"
```

---

## Task 5: Repository (CRUD + idempotency)

**Files:**
- Create: `src/mailagent/store/repository.py`
- Test: `tests/store/test_repository.py`

- [ ] **Step 1: Write the failing test**

`tests/store/test_repository.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/store/test_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.store.repository'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/store/repository.py`:
```python
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from mailagent.store.models import ProcessedMail, Category


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def is_processed(self, uid: str) -> bool:
        stmt = select(ProcessedMail).where(ProcessedMail.uid == uid)
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def mark_processed(self, uid, category, priority, moved, drafted):
        stmt = insert(ProcessedMail).values(
            uid=uid, category=category, priority=priority,
            moved=moved, drafted=drafted,
        ).on_conflict_do_nothing(index_elements=["uid"])
        self.session.execute(stmt)
        self.session.commit()

    def count_processed(self) -> int:
        return self.session.execute(
            select(func.count()).select_from(ProcessedMail)
        ).scalar_one()

    def add_category(self, name: str, description: str = ""):
        stmt = insert(Category).values(
            name=name, description=description
        ).on_conflict_do_nothing(index_elements=["name"])
        self.session.execute(stmt)
        self.session.commit()

    def list_categories(self):
        return self.session.execute(select(Category)).scalars().all()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/store/test_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/store/repository.py tests/store/test_repository.py
git commit -m "feat: add repository with idempotent processed-mail tracking"
```

---

## Task 6: LLM provider abstraction + fake

**Files:**
- Create: `src/mailagent/llm/__init__.py`
- Create: `src/mailagent/llm/provider.py`
- Create: `src/mailagent/llm/fake.py`
- Test: `tests/llm/test_fake.py`
- Create: `tests/llm/__init__.py`

- [ ] **Step 1: Write the failing test**

`tests/llm/__init__.py`: (empty file)

`tests/llm/test_fake.py`:
```python
from mailagent.llm.fake import FakeLLMProvider
from mailagent.llm.provider import Email


def test_fake_classify_returns_configured_category():
    provider = FakeLLMProvider(category="Rechnung", priority="high")
    email = Email(uid="1", subject="Invoice", sender="a@b.c", body="pay now")
    assert provider.classify(email, ["Rechnung", "Newsletter"]) == "Rechnung"


def test_fake_prioritize():
    provider = FakeLLMProvider(category="X", priority="high")
    email = Email(uid="1", subject="s", sender="a@b.c", body="b")
    assert provider.prioritize(email) == "high"


def test_fake_generate_draft_includes_style():
    provider = FakeLLMProvider(draft="Hallo, danke!")
    email = Email(uid="1", subject="s", sender="a@b.c", body="b")
    draft = provider.generate_draft(email, style_examples=["best regards"])
    assert draft == "Hallo, danke!"


def test_fake_embed_returns_fixed_dimension():
    provider = FakeLLMProvider()
    vec = provider.embed("some text")
    assert len(vec) == 1536


def test_fake_chat_returns_answer_with_sources():
    provider = FakeLLMProvider(chat_answer="Sarah said yes.")
    answer = provider.chat("What did Sarah say?", context=["Sarah: yes"])
    assert "Sarah" in answer
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/llm/test_fake.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.llm.fake'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/llm/__init__.py`: (empty file)

`src/mailagent/llm/provider.py`:
```python
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Email:
    uid: str
    subject: str
    sender: str
    body: str
    message_id: str = ""
    in_reply_to: str = ""


class LLMProvider(Protocol):
    def classify(self, email: Email, categories: list[str]) -> str: ...
    def prioritize(self, email: Email) -> str: ...
    def generate_draft(self, email: Email, style_examples: list[str]) -> str: ...
    def embed(self, text: str) -> list[float]: ...
    def chat(self, question: str, context: list[str]) -> str: ...
```

`src/mailagent/llm/fake.py`:
```python
from mailagent.llm.provider import Email


class FakeLLMProvider:
    def __init__(self, category="Sonstiges", priority="medium",
                 draft="(draft)", chat_answer="(answer)"):
        self._category = category
        self._priority = priority
        self._draft = draft
        self._chat_answer = chat_answer

    def classify(self, email: Email, categories: list[str]) -> str:
        return self._category

    def prioritize(self, email: Email) -> str:
        return self._priority

    def generate_draft(self, email: Email, style_examples: list[str]) -> str:
        return self._draft

    def embed(self, text: str) -> list[float]:
        return [0.0] * 1536

    def chat(self, question: str, context: list[str]) -> str:
        if not context:
            return "Keine passende Information gefunden."
        return self._chat_answer
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/llm/test_fake.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/llm tests/llm
git commit -m "feat: add llm provider protocol and fake implementation"
```

---

## Task 7: IMAP client against a test IMAP server

**Files:**
- Create: `src/mailagent/imap/__init__.py`
- Create: `src/mailagent/imap/client.py`
- Modify: `tests/docker-compose.test.yml` (add greenmail service)
- Test: `tests/imap/test_client.py`
- Create: `tests/imap/__init__.py`

- [ ] **Step 1: Write the failing test**

Add greenmail to `tests/docker-compose.test.yml`:
```yaml
  greenmail:
    image: greenmail/standalone:2.0.1
    environment:
      GREENMAIL_OPTS: "-Dgreenmail.setup.test.all -Dgreenmail.users=me:secret@example.com -Dgreenmail.verbose"
    ports:
      - "53143:3143"  # imap
      - "53025:3025"  # smtp
```

`tests/imap/__init__.py`: (empty file)

`tests/imap/test_client.py`:
```python
import smtplib
import time
from email.message import EmailMessage
import pytest
from mailagent.imap.client import ImapClient


def _send(subject, body):
    msg = EmailMessage()
    msg["From"] = "sender@example.com"
    msg["To"] = "me@example.com"
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP("localhost", 53025) as s:
        s.send_message(msg)


@pytest.fixture
def imap(docker_services):
    docker_services.wait_until_responsive(
        timeout=60.0, pause=1.0, check=lambda: ImapClient.can_connect(
            "localhost", 53143, "me@example.com", "secret"))
    return ImapClient(host="localhost", port=53143, user="me@example.com",
                      password="secret", use_ssl=False)


def test_fetch_new_messages(imap):
    _send("Hello", "world")
    time.sleep(1)
    emails = imap.fetch_inbox()
    assert any(e.subject == "Hello" for e in emails)


def test_append_draft(imap):
    imap.append_draft("Draft subject", "Draft body", folder="INBOX")
    emails = imap.fetch_folder("INBOX")
    assert any(e.subject == "Draft subject" for e in emails)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/imap/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.imap.client'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/imap/__init__.py`: (empty file)

`src/mailagent/imap/client.py`:
```python
from imapclient import IMAPClient
from mailagent.llm.provider import Email
import email as email_lib


class ImapClient:
    def __init__(self, host, port, user, password, use_ssl=True,
                 drafts_folder="Drafts", sent_folder="Sent"):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.use_ssl = use_ssl
        self.drafts_folder = drafts_folder
        self.sent_folder = sent_folder

    @staticmethod
    def can_connect(host, port, user, password, use_ssl=False) -> bool:
        try:
            with IMAPClient(host, port=port, ssl=use_ssl) as c:
                c.login(user, password)
            return True
        except Exception:
            return False

    def _connect(self) -> IMAPClient:
        client = IMAPClient(self.host, port=self.port, ssl=self.use_ssl)
        client.login(self.user, self.password)
        return client

    def fetch_inbox(self) -> list[Email]:
        return self.fetch_folder("INBOX")

    def fetch_folder(self, folder: str) -> list[Email]:
        out = []
        with self._connect() as c:
            c.select_folder(folder)
            uids = c.search(["ALL"])
            if not uids:
                return out
            for uid, data in c.fetch(uids, ["RFC822"]).items():
                msg = email_lib.message_from_bytes(data[b"RFC822"])
                out.append(self._to_email(uid, msg))
        return out

    def _to_email(self, uid, msg) -> Email:
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode(errors="replace")
                    break
        else:
            body = msg.get_payload(decode=True).decode(errors="replace")
        return Email(
            uid=str(uid),
            subject=msg.get("Subject", ""),
            sender=msg.get("From", ""),
            body=body,
            message_id=msg.get("Message-ID", ""),
            in_reply_to=msg.get("In-Reply-To", ""),
        )

    def append_draft(self, subject: str, body: str, folder: str | None = None):
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.user
        msg.set_content(body)
        target = folder or self.drafts_folder
        with self._connect() as c:
            c.append(target, msg.as_bytes())

    def move(self, uid: str, target_folder: str, source_folder="INBOX"):
        with self._connect() as c:
            c.select_folder(source_folder)
            c.move([int(uid)], target_folder)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/imap/test_client.py -v`
Expected: PASS (greenmail container handles SMTP send + IMAP fetch/append)

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/imap tests/imap tests/docker-compose.test.yml
git commit -m "feat: add imap client with fetch/append/move"
```

---

## Task 8: Classifier and prioritizer

**Files:**
- Create: `src/mailagent/pipeline/__init__.py`
- Create: `src/mailagent/pipeline/classifier.py`
- Create: `src/mailagent/pipeline/prioritizer.py`
- Test: `tests/pipeline/test_classifier.py`
- Create: `tests/pipeline/__init__.py`

- [ ] **Step 1: Write the failing test**

`tests/pipeline/__init__.py`: (empty file)

`tests/pipeline/test_classifier.py`:
```python
from mailagent.llm.fake import FakeLLMProvider
from mailagent.llm.provider import Email
from mailagent.pipeline.classifier import Classifier
from mailagent.pipeline.prioritizer import Prioritizer

EMAIL = Email(uid="1", subject="s", sender="a@b.c", body="b")


def test_classifier_returns_known_category():
    clf = Classifier(FakeLLMProvider(category="Newsletter"))
    assert clf.classify(EMAIL, ["Newsletter", "Rechnung"]) == "Newsletter"


def test_classifier_unknown_category_falls_back():
    clf = Classifier(FakeLLMProvider(category="Bogus"))
    assert clf.classify(EMAIL, ["Newsletter"]) == "unklassifiziert"


def test_prioritizer_valid_level():
    pri = Prioritizer(FakeLLMProvider(priority="high"))
    assert pri.prioritize(EMAIL) == "high"


def test_prioritizer_invalid_defaults_medium():
    pri = Prioritizer(FakeLLMProvider(priority="banana"))
    assert pri.prioritize(EMAIL) == "medium"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/test_classifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.pipeline.classifier'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/pipeline/__init__.py`: (empty file)

`src/mailagent/pipeline/classifier.py`:
```python
from mailagent.llm.provider import LLMProvider, Email


class Classifier:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def classify(self, email: Email, categories: list[str]) -> str:
        result = self.provider.classify(email, categories)
        if result not in categories:
            return "unklassifiziert"
        return result
```

`src/mailagent/pipeline/prioritizer.py`:
```python
from mailagent.llm.provider import LLMProvider, Email

VALID = {"high", "medium", "low"}


class Prioritizer:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def prioritize(self, email: Email) -> str:
        result = self.provider.prioritize(email)
        return result if result in VALID else "medium"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipeline/test_classifier.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/pipeline/__init__.py src/mailagent/pipeline/classifier.py src/mailagent/pipeline/prioritizer.py tests/pipeline
git commit -m "feat: add classifier and prioritizer"
```

---

## Task 9: Mover (category -> folder mapping)

**Files:**
- Create: `src/mailagent/pipeline/mover.py`
- Test: `tests/pipeline/test_mover.py`

- [ ] **Step 1: Write the failing test**

`tests/pipeline/test_mover.py`:
```python
from mailagent.pipeline.mover import Mover


class FakeImap:
    def __init__(self):
        self.moved = []

    def move(self, uid, target_folder, source_folder="INBOX"):
        self.moved.append((uid, target_folder))


def test_move_applies_mapping():
    imap = FakeImap()
    mover = Mover(imap, mapping={"Newsletter": "Archive/News"})
    moved = mover.maybe_move("uid-1", "Newsletter")
    assert moved is True
    assert imap.moved == [("uid-1", "Archive/News")]


def test_no_mapping_means_no_move():
    imap = FakeImap()
    mover = Mover(imap, mapping={"Newsletter": "Archive/News"})
    moved = mover.maybe_move("uid-2", "Rechnung")
    assert moved is False
    assert imap.moved == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/test_mover.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.pipeline.mover'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/pipeline/mover.py`:
```python
class Mover:
    def __init__(self, imap_client, mapping: dict[str, str]):
        self.imap = imap_client
        self.mapping = mapping

    def maybe_move(self, uid: str, category: str) -> bool:
        target = self.mapping.get(category)
        if not target:
            return False
        self.imap.move(uid, target)
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipeline/test_mover.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/pipeline/mover.py tests/pipeline/test_mover.py
git commit -m "feat: add category-to-folder mover"
```

---

## Task 10: Draft generator (generate + append + store reference)

**Files:**
- Create: `src/mailagent/pipeline/draft_generator.py`
- Test: `tests/pipeline/test_draft_generator.py`

- [ ] **Step 1: Write the failing test**

`tests/pipeline/test_draft_generator.py`:
```python
import pytest
from mailagent.store.models import Base, ReferenceDraft
from mailagent.llm.fake import FakeLLMProvider
from mailagent.llm.provider import Email
from mailagent.pipeline.draft_generator import DraftGenerator
from sqlalchemy import select


class FakeImap:
    def __init__(self):
        self.drafts = []

    def append_draft(self, subject, body, folder=None):
        self.drafts.append((subject, body))


@pytest.fixture
def session(db_engine, db_session):
    Base.metadata.create_all(db_engine)
    return db_session


def test_generate_appends_draft_and_stores_reference(session):
    imap = FakeImap()
    gen = DraftGenerator(FakeLLMProvider(draft="Hallo, danke."), imap, session)
    email = Email(uid="1", subject="Frage", sender="a@b.c", body="?",
                  message_id="<m1>")
    gen.generate(email, style_examples=["Mit besten Grüßen"])
    assert imap.drafts == [("Re: Frage", "Hallo, danke.")]
    refs = session.execute(select(ReferenceDraft)).scalars().all()
    assert len(refs) == 1
    assert refs[0].source_uid == "1"
    assert refs[0].content == "Hallo, danke."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/test_draft_generator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.pipeline.draft_generator'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/pipeline/draft_generator.py`:
```python
from mailagent.llm.provider import LLMProvider, Email
from mailagent.store.models import ReferenceDraft


class DraftGenerator:
    def __init__(self, provider: LLMProvider, imap_client, session):
        self.provider = provider
        self.imap = imap_client
        self.session = session

    def generate(self, email: Email, style_examples: list[str]) -> str:
        content = self.provider.generate_draft(email, style_examples)
        subject = email.subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        self.imap.append_draft(subject, content)
        self.session.add(ReferenceDraft(
            source_uid=email.uid,
            message_id=email.message_id,
            content=content,
        ))
        self.session.commit()
        return content
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipeline/test_draft_generator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/pipeline/draft_generator.py tests/pipeline/test_draft_generator.py
git commit -m "feat: add draft generator with reference draft storage"
```

---

## Task 11: Indexer (embed + store mail content)

**Files:**
- Create: `src/mailagent/pipeline/indexer.py`
- Test: `tests/pipeline/test_indexer.py`

- [ ] **Step 1: Write the failing test**

`tests/pipeline/test_indexer.py`:
```python
import pytest
from sqlalchemy import select
from mailagent.store.models import Base, MailIndex
from mailagent.llm.fake import FakeLLMProvider
from mailagent.llm.provider import Email
from mailagent.pipeline.indexer import Indexer


@pytest.fixture
def session(db_engine, db_session):
    Base.metadata.create_all(db_engine)
    return db_session


def test_index_stores_embedding(session):
    idx = Indexer(FakeLLMProvider(), session)
    email = Email(uid="1", subject="Budget", sender="sarah@x.c", body="approved")
    idx.index(email)
    rows = session.execute(select(MailIndex)).scalars().all()
    assert len(rows) == 1
    assert rows[0].uid == "1"
    assert len(rows[0].embedding) == 1536


def test_index_is_idempotent(session):
    idx = Indexer(FakeLLMProvider(), session)
    email = Email(uid="2", subject="s", sender="a@b.c", body="b")
    idx.index(email)
    idx.index(email)
    rows = session.execute(select(MailIndex)).scalars().all()
    assert len(rows) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/test_indexer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.pipeline.indexer'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/pipeline/indexer.py`:
```python
from sqlalchemy.dialects.postgresql import insert
from mailagent.llm.provider import LLMProvider, Email
from mailagent.store.models import MailIndex


class Indexer:
    def __init__(self, provider: LLMProvider, session):
        self.provider = provider
        self.session = session

    def index(self, email: Email):
        text = f"{email.subject}\n{email.body}"
        embedding = self.provider.embed(text)
        stmt = insert(MailIndex).values(
            uid=email.uid, subject=email.subject, sender=email.sender,
            body=email.body, embedding=embedding,
        ).on_conflict_do_nothing(index_elements=["uid"])
        self.session.execute(stmt)
        self.session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipeline/test_indexer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/pipeline/indexer.py tests/pipeline/test_indexer.py
git commit -m "feat: add mail indexer with pgvector embeddings"
```

---

## Task 12: Audit log writer

**Files:**
- Create: `src/mailagent/audit/__init__.py`
- Create: `src/mailagent/audit/log.py`
- Test: `tests/audit/test_log.py`
- Create: `tests/audit/__init__.py`

- [ ] **Step 1: Write the failing test**

`tests/audit/__init__.py`: (empty file)

`tests/audit/test_log.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/audit/test_log.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.audit.log'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/audit/__init__.py`: (empty file)

`src/mailagent/audit/log.py`:
```python
from mailagent.store.models import AuditLog


class AuditLogger:
    def __init__(self, session):
        self.session = session

    def record(self, actor: str, action: str, target: str = "",
               result: str = "success"):
        self.session.add(AuditLog(
            actor=actor, action=action, target=target, result=result,
        ))
        self.session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/audit/test_log.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/audit tests/audit
git commit -m "feat: add append-only audit logger"
```

---

## Task 13: Style learner (bootstrap from Sent)

**Files:**
- Create: `src/mailagent/learning/__init__.py`
- Create: `src/mailagent/learning/style_learner.py`
- Test: `tests/learning/test_style_learner.py`
- Create: `tests/learning/__init__.py`

- [ ] **Step 1: Write the failing test**

`tests/learning/__init__.py`: (empty file)

`tests/learning/test_style_learner.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/learning/test_style_learner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.learning.style_learner'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/learning/__init__.py`: (empty file)

`src/mailagent/learning/style_learner.py`:
```python
from sqlalchemy import select, desc
from mailagent.store.models import StyleExample


class StyleLearner:
    def __init__(self, imap_client, session, sample_size: int = 50):
        self.imap = imap_client
        self.session = session
        self.sample_size = sample_size

    def bootstrap(self) -> int:
        sent = self.imap.fetch_folder(self.imap.sent_folder)[: self.sample_size]
        count = 0
        for email in sent:
            self.session.add(StyleExample(
                content=email.body, source="bootstrap", weight=1.0,
            ))
            count += 1
        self.session.commit()
        return count

    def get_style_examples(self, limit: int = 10) -> list[str]:
        stmt = (select(StyleExample)
                .order_by(desc(StyleExample.weight))
                .limit(limit))
        return [r.content for r in self.session.execute(stmt).scalars().all()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/learning/test_style_learner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/learning/__init__.py src/mailagent/learning/style_learner.py tests/learning
git commit -m "feat: add style learner bootstrap from sent folder"
```

---

## Task 14: Feedback learner (draft <-> sent diff)

**Files:**
- Create: `src/mailagent/learning/feedback_learner.py`
- Test: `tests/learning/test_feedback_learner.py`

- [ ] **Step 1: Write the failing test**

`tests/learning/test_feedback_learner.py`:
```python
import pytest
from sqlalchemy import select
from mailagent.store.models import Base, ReferenceDraft, StyleExample
from mailagent.llm.provider import Email
from mailagent.learning.feedback_learner import FeedbackLearner


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/learning/test_feedback_learner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.learning.feedback_learner'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/learning/feedback_learner.py`:
```python
from difflib import SequenceMatcher
from sqlalchemy import select
from mailagent.store.models import ReferenceDraft, StyleExample


class FeedbackLearner:
    def __init__(self, imap_client, session):
        self.imap = imap_client
        self.session = session

    def run(self) -> int:
        sent = self.imap.fetch_folder(self.imap.sent_folder)
        matched = 0
        for email in sent:
            ref = self._match(email)
            if ref is None:
                continue
            ratio = SequenceMatcher(None, ref.content, email.body).ratio()
            # more editing (lower ratio) -> stronger correction signal
            weight = 1.0 + (1.0 - ratio)
            self.session.add(StyleExample(
                content=email.body, source="feedback", weight=weight,
            ))
            matched += 1
        self.session.commit()
        return matched

    def _match(self, email) -> ReferenceDraft | None:
        if not email.in_reply_to:
            return None
        stmt = select(ReferenceDraft).where(
            ReferenceDraft.message_id == email.in_reply_to)
        return self.session.execute(stmt).scalar_one_or_none()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/learning/test_feedback_learner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/learning/feedback_learner.py tests/learning/test_feedback_learner.py
git commit -m "feat: add feedback learner with draft-sent diff weighting"
```

---

## Task 15: Chat (vector retrieval + answer)

**Files:**
- Create: `src/mailagent/chat/__init__.py`
- Create: `src/mailagent/chat/chat.py`
- Test: `tests/chat/test_chat.py`
- Create: `tests/chat/__init__.py`

- [ ] **Step 1: Write the failing test**

`tests/chat/__init__.py`: (empty file)

`tests/chat/test_chat.py`:
```python
import pytest
from mailagent.store.models import Base, MailIndex
from mailagent.llm.fake import FakeLLMProvider
from mailagent.chat.chat import Chat


@pytest.fixture
def session(db_engine, db_session):
    Base.metadata.create_all(db_engine)
    return db_session


def _add_mail(session, uid, body, vec):
    session.add(MailIndex(uid=uid, subject="s", sender="sarah@x.c",
                          body=body, embedding=vec))
    session.commit()


def test_chat_returns_answer_with_context(session):
    _add_mail(session, "1", "Sarah approved the Q4 budget", [0.1] * 1536)
    provider = FakeLLMProvider(chat_answer="Sarah approved it.")
    chat = Chat(provider, session)
    answer = chat.ask("What did Sarah say about the budget?")
    assert "Sarah" in answer.text
    assert "1" in [s.uid for s in answer.sources]


def test_chat_empty_index_returns_no_info(session):
    chat = Chat(FakeLLMProvider(), session)
    answer = chat.ask("anything?")
    assert "Keine passende Information" in answer.text
    assert answer.sources == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/chat/test_chat.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.chat.chat'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/chat/__init__.py`: (empty file)

`src/mailagent/chat/chat.py`:
```python
from dataclasses import dataclass
from sqlalchemy import select
from mailagent.llm.provider import LLMProvider
from mailagent.store.models import MailIndex


@dataclass
class ChatSource:
    uid: str
    subject: str


@dataclass
class ChatAnswer:
    text: str
    sources: list[ChatSource]


class Chat:
    def __init__(self, provider: LLMProvider, session, top_k: int = 5):
        self.provider = provider
        self.session = session
        self.top_k = top_k

    def ask(self, question: str) -> ChatAnswer:
        query_vec = self.provider.embed(question)
        stmt = (select(MailIndex)
                .order_by(MailIndex.embedding.cosine_distance(query_vec))
                .limit(self.top_k))
        rows = self.session.execute(stmt).scalars().all()
        if not rows:
            return ChatAnswer(text="Keine passende Information gefunden.",
                              sources=[])
        context = [f"{r.sender}: {r.body}" for r in rows]
        text = self.provider.chat(question, context)
        sources = [ChatSource(uid=r.uid, subject=r.subject) for r in rows]
        return ChatAnswer(text=text, sources=sources)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/chat/test_chat.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/chat tests/chat
git commit -m "feat: add mailbox chat with pgvector retrieval"
```

---

## Task 16: Scheduler runner (main run wiring)

**Files:**
- Create: `src/mailagent/scheduler/__init__.py`
- Create: `src/mailagent/scheduler/runner.py`
- Test: `tests/scheduler/test_runner.py`
- Create: `tests/scheduler/__init__.py`

- [ ] **Step 1: Write the failing test**

`tests/scheduler/__init__.py`: (empty file)

`tests/scheduler/test_runner.py`:
```python
import pytest
from mailagent.store.models import Base
from mailagent.store.repository import Repository
from mailagent.llm.fake import FakeLLMProvider
from mailagent.llm.provider import Email
from mailagent.scheduler.runner import Runner


class FakeImap:
    def __init__(self, inbox):
        self._inbox = inbox
        self.drafts = []
        self.moved = []
        self.drafts_folder = "Drafts"
        self.sent_folder = "Sent"

    def fetch_inbox(self):
        return self._inbox

    def append_draft(self, subject, body, folder=None):
        self.drafts.append((subject, body))

    def move(self, uid, target_folder, source_folder="INBOX"):
        self.moved.append((uid, target_folder))


@pytest.fixture
def session(db_engine, db_session):
    Base.metadata.create_all(db_engine)
    return db_session


def test_main_run_classifies_and_drafts_for_reply_needed(session):
    inbox = [Email(uid="1", subject="Frage", sender="a@b.c", body="?",
                   message_id="<m1>")]
    imap = FakeImap(inbox)
    provider = FakeLLMProvider(category="Antwort nötig", priority="high",
                               draft="Hallo!")
    runner = Runner(
        imap=imap, provider=provider, session=session,
        categories=["Antwort nötig", "Newsletter"],
        mapping={}, reply_category="Antwort nötig",
        style_examples=["Grüße"],
    )
    runner.run_main()
    assert Repository(session).is_processed("1")
    assert imap.drafts == [("Re: Frage", "Hallo!")]


def test_main_run_skips_already_processed(session):
    Repository(session).mark_processed("1", "X", "low", False, False)
    inbox = [Email(uid="1", subject="x", sender="a@b.c", body="b")]
    imap = FakeImap(inbox)
    runner = Runner(
        imap=imap, provider=FakeLLMProvider(), session=session,
        categories=["X"], mapping={}, reply_category="Antwort nötig",
        style_examples=[],
    )
    runner.run_main()
    assert imap.drafts == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scheduler/test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.scheduler.runner'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/scheduler/__init__.py`: (empty file)

`src/mailagent/scheduler/runner.py`:
```python
from mailagent.store.repository import Repository
from mailagent.pipeline.classifier import Classifier
from mailagent.pipeline.prioritizer import Prioritizer
from mailagent.pipeline.mover import Mover
from mailagent.pipeline.draft_generator import DraftGenerator
from mailagent.pipeline.indexer import Indexer
from mailagent.audit.log import AuditLogger


class Runner:
    def __init__(self, imap, provider, session, categories, mapping,
                 reply_category, style_examples):
        self.imap = imap
        self.session = session
        self.repo = Repository(session)
        self.categories = categories
        self.reply_category = reply_category
        self.style_examples = style_examples
        self.classifier = Classifier(provider)
        self.prioritizer = Prioritizer(provider)
        self.mover = Mover(imap, mapping)
        self.draft_generator = DraftGenerator(provider, imap, session)
        self.indexer = Indexer(provider, session)
        self.audit = AuditLogger(session)

    def run_main(self):
        for email in self.imap.fetch_inbox():
            if self.repo.is_processed(email.uid):
                continue
            try:
                category = self.classifier.classify(email, self.categories)
                priority = self.prioritizer.prioritize(email)
                self.indexer.index(email)
                moved = self.mover.maybe_move(email.uid, category)
                drafted = False
                if category == self.reply_category:
                    self.draft_generator.generate(email, self.style_examples)
                    self.audit.record("scheduler", "draft_append", email.uid)
                    drafted = True
                self.repo.mark_processed(
                    email.uid, category, priority, moved, drafted)
            except Exception as exc:  # per-mail isolation
                self.audit.record("scheduler", "process_error",
                                  email.uid, result="error")
                continue
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/scheduler/test_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/scheduler tests/scheduler
git commit -m "feat: add scheduler main run wiring pipeline together"
```

---

## Task 17: CLI (Typer)

**Files:**
- Create: `src/mailagent/cli/__init__.py`
- Create: `src/mailagent/cli/main.py`
- Test: `tests/cli/test_main.py`
- Create: `tests/cli/__init__.py`

- [ ] **Step 1: Write the failing test**

`tests/cli/__init__.py`: (empty file)

`tests/cli/test_main.py`:
```python
from typer.testing import CliRunner
from mailagent.cli.main import app

runner = CliRunner()


def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_categories_list_command(monkeypatch):
    from mailagent.cli import main

    class FakeRepo:
        def list_categories(self):
            class C:
                name = "Newsletter"
            return [C()]

    monkeypatch.setattr(main, "_make_repo", lambda: FakeRepo())
    result = runner.invoke(app, ["categories"])
    assert result.exit_code == 0
    assert "Newsletter" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cli/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.cli.main'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/cli/__init__.py`: (empty file)

`src/mailagent/cli/main.py`:
```python
import typer
from mailagent import __version__

app = typer.Typer(help="Mailagent CLI")


def _make_repo():
    from mailagent.config import load_config
    from mailagent.store.db import make_engine, make_session_factory
    from mailagent.store.repository import Repository
    cfg = load_config()
    engine = make_engine(cfg.database_url)
    session = make_session_factory(engine)()
    return Repository(session)


@app.command()
def version():
    """Print the version."""
    typer.echo(__version__)


@app.command()
def categories():
    """List configured categories."""
    repo = _make_repo()
    for c in repo.list_categories():
        typer.echo(c.name)


@app.command()
def run():
    """Trigger a main run now."""
    typer.echo("Triggering main run...")
    # Wiring to Runner is done in deployment task; kept thin here.


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/cli/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/cli tests/cli
git commit -m "feat: add typer cli with version and categories commands"
```

---

## Task 18: Web API (FastAPI) with auth

**Files:**
- Create: `src/mailagent/api/__init__.py`
- Create: `src/mailagent/api/app.py`
- Create: `src/mailagent/api/routes.py`
- Test: `tests/api/test_app.py`
- Create: `tests/api/__init__.py`

- [ ] **Step 1: Write the failing test**

`tests/api/__init__.py`: (empty file)

`tests/api/test_app.py`:
```python
from fastapi.testclient import TestClient
from mailagent.api.app import create_app


def test_health_no_auth_required():
    client = TestClient(create_app(api_token="secret-token"))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_categories_requires_auth():
    client = TestClient(create_app(api_token="secret-token"))
    resp = client.get("/categories")
    assert resp.status_code == 401


def test_categories_with_valid_token():
    app = create_app(api_token="secret-token")

    class FakeRepo:
        def list_categories(self):
            class C:
                name = "Newsletter"
            return [C()]

    app.state.repo_factory = lambda: FakeRepo()
    client = TestClient(app)
    resp = client.get("/categories",
                      headers={"Authorization": "Bearer secret-token"})
    assert resp.status_code == 200
    assert resp.json() == ["Newsletter"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.api.app'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/api/__init__.py`: (empty file)

`src/mailagent/api/app.py`:
```python
from fastapi import FastAPI, Depends, HTTPException, Header
from mailagent.api import routes


def create_app(api_token: str) -> FastAPI:
    app = FastAPI(title="Mailagent")
    app.state.api_token = api_token
    app.state.repo_factory = None

    def require_auth(authorization: str = Header(default="")):
        expected = f"Bearer {app.state.api_token}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/categories", dependencies=[Depends(require_auth)])
    def categories():
        return routes.list_categories(app.state.repo_factory())

    return app
```

`src/mailagent/api/routes.py`:
```python
def list_categories(repo) -> list[str]:
    return [c.name for c in repo.list_categories()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/api tests/api
git commit -m "feat: add fastapi web api with token auth"
```

---

## Task 19: OpenAI provider (real implementation)

**Files:**
- Create: `src/mailagent/llm/openai_provider.py`
- Test: `tests/llm/test_openai_provider.py`

- [ ] **Step 1: Write the failing test**

`tests/llm/test_openai_provider.py`:
```python
from mailagent.llm.openai_provider import OpenAIProvider
from mailagent.llm.provider import Email


class FakeChatResponse:
    def __init__(self, content):
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})})]


class FakeEmbeddingResponse:
    def __init__(self, vec):
        self.data = [type("D", (), {"embedding": vec})]


class FakeClient:
    def __init__(self, content="Newsletter", vec=None):
        self._content = content
        self._vec = vec or [0.0] * 1536

        class Chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return FakeChatResponse(content)
        class Embeddings:
            @staticmethod
            def create(**kwargs):
                return FakeEmbeddingResponse(self_vec=None)

        self.chat = Chat()
        self.embeddings = type("E", (), {
            "create": staticmethod(lambda **kw: FakeEmbeddingResponse(self._vec))
        })()


def test_classify_uses_chat_completion():
    provider = OpenAIProvider(client=FakeClient(content="Newsletter"))
    email = Email(uid="1", subject="s", sender="a@b.c", body="b")
    assert provider.classify(email, ["Newsletter", "Rechnung"]) == "Newsletter"


def test_embed_returns_vector():
    provider = OpenAIProvider(client=FakeClient(vec=[0.5] * 1536))
    assert provider.embed("text") == [0.5] * 1536
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/llm/test_openai_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailagent.llm.openai_provider'`

- [ ] **Step 3: Write the implementation**

`src/mailagent/llm/openai_provider.py`:
```python
from mailagent.llm.provider import Email

CLASSIFY_PROMPT = (
    "Classify this email into exactly one of these categories: {categories}.\n"
    "Reply with only the category name.\n\nSubject: {subject}\n\n{body}"
)
PRIORITY_PROMPT = (
    "Rate the urgency of this email as exactly one word: high, medium, or low.\n\n"
    "Subject: {subject}\n\n{body}"
)
DRAFT_PROMPT = (
    "Write a reply to the email below. Match the writing style shown in these "
    "examples:\n{style}\n\n---\nEmail:\nSubject: {subject}\n\n{body}"
)
CHAT_PROMPT = (
    "Answer the question using only the email context below. If the context "
    "does not contain the answer, say you found no matching information.\n\n"
    "Context:\n{context}\n\nQuestion: {question}"
)


class OpenAIProvider:
    def __init__(self, client, model="gpt-4o-mini",
                 embed_model="text-embedding-3-small"):
        self.client = client
        self.model = model
        self.embed_model = embed_model

    def _chat(self, prompt: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content.strip()

    def classify(self, email: Email, categories: list[str]) -> str:
        return self._chat(CLASSIFY_PROMPT.format(
            categories=", ".join(categories),
            subject=email.subject, body=email.body))

    def prioritize(self, email: Email) -> str:
        return self._chat(PRIORITY_PROMPT.format(
            subject=email.subject, body=email.body)).lower()

    def generate_draft(self, email: Email, style_examples: list[str]) -> str:
        return self._chat(DRAFT_PROMPT.format(
            style="\n---\n".join(style_examples),
            subject=email.subject, body=email.body))

    def embed(self, text: str) -> list[float]:
        resp = self.client.embeddings.create(model=self.embed_model, input=text)
        return list(resp.data[0].embedding)

    def chat(self, question: str, context: list[str]) -> str:
        return self._chat(CHAT_PROMPT.format(
            context="\n\n".join(context), question=question))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/llm/test_openai_provider.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/llm/openai_provider.py tests/llm/test_openai_provider.py
git commit -m "feat: add openai llm provider implementation"
```

---

## Task 20: Provider factory + scheduled loop entrypoint

**Files:**
- Create: `src/mailagent/llm/factory.py`
- Modify: `src/mailagent/scheduler/runner.py` (add `run_style` and `run_feedback`)
- Test: `tests/llm/test_factory.py`
- Test: `tests/scheduler/test_runner_extra.py`

- [ ] **Step 1: Write the failing test**

`tests/llm/test_factory.py`:
```python
from mailagent.llm.factory import make_provider
from mailagent.llm.fake import FakeLLMProvider


def test_factory_returns_fake():
    provider = make_provider("fake", api_key=None)
    assert isinstance(provider, FakeLLMProvider)


def test_factory_unknown_raises():
    import pytest
    with pytest.raises(ValueError):
        make_provider("nope", api_key=None)
```

`tests/scheduler/test_runner_extra.py`:
```python
import pytest
from mailagent.store.models import Base, StyleExample
from mailagent.llm.fake import FakeLLMProvider
from mailagent.llm.provider import Email
from mailagent.scheduler.runner import Runner
from sqlalchemy import select


class FakeImap:
    def __init__(self, sent):
        self._sent = sent
        self.sent_folder = "Sent"
        self.drafts_folder = "Drafts"

    def fetch_inbox(self):
        return []

    def fetch_folder(self, folder):
        return self._sent


@pytest.fixture
def session(db_engine, db_session):
    Base.metadata.create_all(db_engine)
    return db_session


def test_run_style_bootstraps(session):
    sent = [Email(uid="1", subject="s", sender="me@x.c", body="Grüße")]
    runner = Runner(imap=FakeImap(sent), provider=FakeLLMProvider(),
                    session=session, categories=["X"], mapping={},
                    reply_category="Antwort nötig", style_examples=[])
    runner.run_style()
    rows = session.execute(select(StyleExample)).scalars().all()
    assert len(rows) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/llm/test_factory.py tests/scheduler/test_runner_extra.py -v`
Expected: FAIL — `mailagent.llm.factory` missing; `Runner.run_style` missing.

- [ ] **Step 3: Write the implementation**

`src/mailagent/llm/factory.py`:
```python
from mailagent.llm.fake import FakeLLMProvider


def make_provider(name: str, api_key):
    if name == "fake":
        return FakeLLMProvider()
    if name == "openai":
        from openai import OpenAI
        from mailagent.llm.openai_provider import OpenAIProvider
        return OpenAIProvider(client=OpenAI(api_key=api_key))
    raise ValueError(f"Unknown provider: {name}")
```

Add `openai>=1.0` to `pyproject.toml` dependencies.

Add to `src/mailagent/scheduler/runner.py` (new methods on `Runner`, and import at top):
```python
from mailagent.learning.style_learner import StyleLearner
from mailagent.learning.feedback_learner import FeedbackLearner
```
```python
    def run_style(self):
        StyleLearner(self.imap, self.session).bootstrap()

    def run_feedback(self):
        FeedbackLearner(self.imap, self.session).run()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/llm/test_factory.py tests/scheduler/test_runner_extra.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mailagent/llm/factory.py src/mailagent/scheduler/runner.py tests/llm/test_factory.py tests/scheduler/test_runner_extra.py pyproject.toml
git commit -m "feat: add provider factory and style/feedback runs"
```

---

## Task 21: Deployment (Dockerfile + docker-compose) and full test run

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `README.md`

- [ ] **Step 1: Write the Dockerfile**

`Dockerfile`:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install --no-cache-dir -e .
CMD ["uvicorn", "mailagent.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write docker-compose.yml**

`docker-compose.yml`:
```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      POSTGRES_DB: mailagent
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
  app:
    build: .
    env_file: .env
    depends_on:
      - postgres
    ports:
      - "8000:8000"
volumes:
  pgdata:
```

`.env.example`:
```
MAILAGENT_DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/mailagent
MAILAGENT_IMAP_HOST=imap.example.com
MAILAGENT_IMAP_USER=me@example.com
MAILAGENT_IMAP_PASSWORD=changeme
MAILAGENT_LLM_PROVIDER=openai
MAILAGENT_LLM_API_KEY=sk-...
MAILAGENT_SCHEDULE_MINUTES=15
MAILAGENT_API_TOKEN=change-this-token
```

`README.md`: brief usage — `docker compose up`, run `alembic upgrade head`, CLI via `docker compose exec app mailagent --help`.

- [ ] **Step 3: Run the full test suite**

Run: `pytest -v`
Expected: PASS — all tests across store, llm, imap, pipeline, learning, chat, scheduler, cli, api green. Test containers (postgres+pgvector, greenmail) start via pytest-docker.

- [ ] **Step 4: Verify the image builds**

Run: `docker compose build`
Expected: Build succeeds with no errors.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml .env.example README.md
git commit -m "chore: add docker deployment and project readme"
```

---

## Self-Review Notes

- **Spec coverage:** IMAP fetch/move/append (T7), classify (T8), prioritize (T8),
  category+folder mapping (T9), auto-draft for reply-needed + IMAP draft (T10, T16),
  index for chat (T11), audit log (T12), style bootstrap (T13), feedback loop (T14),
  AI-chat with pgvector (T15), scheduler main/style/feedback runs (T16, T20),
  configurable provider cloud-default (T6, T19, T20), CLI (T17), Web API + auth (T18),
  Postgres store + migrations (T3, T4, T5), no auto-send (no SMTP-send anywhere),
  credentials only from env (T2), docker-compose two-container deploy (T21).
- **Type consistency:** `Email` dataclass fields (uid, subject, sender, body,
  message_id, in_reply_to) used consistently across all modules. `LLMProvider`
  methods (classify/prioritize/generate_draft/embed/chat) match in fake, openai,
  and all consumers. `Repository.mark_processed` signature consistent in T5 and T16.
