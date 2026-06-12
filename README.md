# mailbender

Self-hosted **e-mail sorting and reply-draft agent**. It connects to a generic
IMAP/SMTP mailbox, classifies and prioritizes incoming mail, optionally moves it
into IMAP folders, generates reply drafts in your learned writing style (stored
as IMAP drafts — it never sends mail itself), and lets you ask questions about
your mailbox via AI chat. A shared `core` package is exposed through both a CLI
and a self-hosted web API.

## Tech stack

Python 3.12 · FastAPI · Typer · SQLAlchemy 2 + Alembic · PostgreSQL + pgvector ·
IMAPClient · pluggable LLM provider (cloud default, configurable).

## Quick start

1. Copy and edit the environment file:

   ```bash
   cp .env.example .env
   # set IMAP credentials, LLM provider/key, and MAILAGENT_API_TOKEN
   ```

2. Start the stack (app + Postgres with pgvector):

   ```bash
   docker compose up -d
   ```

3. Apply database migrations:

   ```bash
   docker compose exec app alembic upgrade head
   ```

4. The web API is now on http://localhost:8000 (`GET /health` is public; other
   endpoints require `Authorization: Bearer $MAILAGENT_API_TOKEN`).

## CLI

```bash
docker compose exec app mailagent --help
docker compose exec app mailagent version
docker compose exec app mailagent categories
```

## Configuration

All configuration is read from environment variables (prefix `MAILAGENT_`); see
`.env.example` for the full list. IMAP settings use the nested `MAILAGENT_IMAP_`
prefix (host, user, password, port, drafts/sent folders).

## Development

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

The test suite uses `pytest-docker` to spin up disposable Postgres (pgvector) and
GreenMail (IMAP/SMTP) containers, so Docker must be running locally.
