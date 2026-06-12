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
   # set IMAP credentials, LLM provider/key, and MAILBENDER_API_TOKEN
   ```

2. Start the stack (app + scheduler + Postgres with pgvector):

   ```bash
   docker compose up -d
   ```

   This starts three services: `postgres`, the `app` (web API), and a
   `scheduler` that runs the periodic main/feedback/style passes. The `app` and
   `scheduler` wait for Postgres to pass its health check, then run database
   migrations (`alembic upgrade head`) automatically on container start.

3. The web API is now on http://localhost:8000 (`GET /health` is public; all
   other endpoints require `Authorization: Bearer $MAILBENDER_API_TOKEN`):

   - `POST /chat` `{"question": "..."}` — ask about the mailbox
   - `POST /run` — trigger a main run now
   - `GET /priorities` — processed mail sorted by priority
   - `GET /history` / `GET /audit` — recent run history / audit log
   - `GET/POST/DELETE /mappings` — manage category→folder mappings
   - `GET /categories` — list categories

## Scheduling

The `scheduler` service loops continuously, firing each run type on its own
cadence (minutes): `MAILBENDER_SCHEDULE_MINUTES` (main), `MAILBENDER_FEEDBACK_MINUTES`,
`MAILBENDER_STYLE_MINUTES`. A value of `0` disables automatic runs for that type
(style learning defaults to `0` = manual/CLI only).

## CLI

```bash
docker compose exec app mailbender --help
docker compose exec app mailbender scheduler          # run the loop in foreground
docker compose exec app mailbender run                # one main pass now
docker compose exec app mailbender run-style          # bootstrap style from Sent
docker compose exec app mailbender run-feedback       # draft-vs-sent feedback pass
docker compose exec app mailbender chat "What did Sarah say about the budget?"
docker compose exec app mailbender priorities         # mail by priority (high first)
docker compose exec app mailbender history            # recent run history
docker compose exec app mailbender audit              # recent audit-log entries
docker compose exec app mailbender categories         # list categories
docker compose exec app mailbender add-mapping Newsletter Archive/News
docker compose exec app mailbender mappings
docker compose exec app mailbender remove-mapping Newsletter
```

## Audit log

Security-relevant actions are written to an append-only audit log, viewable via
`mailbender audit` or `GET /audit`: failed API auth attempts, configuration
changes (categories and folder mappings), manually triggered runs, chat queries
(without the question or any mail content), and mailbox writes (moves and
draft-appends). Each entry records a timestamp, actor, action, target, and
result — never credentials, API keys, or message content.

## Configuration

All configuration is read from environment variables (prefix `MAILBENDER_`); see
`.env.example` for the full list. IMAP settings use the nested `MAILBENDER_IMAP_`
prefix (host, user, password, port, drafts/sent folders). The web API token is
`MAILBENDER_API_TOKEN`; the deployed server (`uvicorn
mailbender.api.bootstrap:production_app --factory`) reads it from the
environment and requires it on every endpoint except `GET /health`.

## Development

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

The test suite uses `pytest-docker` to spin up disposable Postgres (pgvector) and
GreenMail (IMAP/SMTP) containers, so Docker must be running locally.
