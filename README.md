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

## CLI (thin client)

Install on your machine — no server stack required. The thin client is published
as a wheel on each [GitHub Release](https://github.com/phreatom/mailbender/releases).
Install the latest release's wheel directly by URL (replace `v0.1.0` with the
release you want):

```bash
# uv (recommended):
uv tool install https://github.com/phreatom/mailbender/releases/download/v0.1.0/mailbender-0.1.0-py3-none-any.whl

# or pipx:
pipx install https://github.com/phreatom/mailbender/releases/download/v0.1.0/mailbender-0.1.0-py3-none-any.whl

# or pip into the current environment:
pip install https://github.com/phreatom/mailbender/releases/download/v0.1.0/mailbender-0.1.0-py3-none-any.whl
```

Or download `mailbender-<version>-py3-none-any.whl` (or the `.tar.gz` sdist) from
the [Releases page](https://github.com/phreatom/mailbender/releases) and install
the local file, e.g. `uv tool install ./mailbender-0.1.0-py3-none-any.whl`.

Then log in to your server's API:

```bash
mailbender login                # prompts for API URL + token; writes ~/.config/mailbender/config.toml (chmod 600)
```

> Once the package is published to PyPI, `uv tool install mailbender` /
> `pipx install mailbender` will work without the release URL.

URL/token resolution order is **flag > env (`MAILBENDER_API_URL` / `MAILBENDER_API_TOKEN`) > config file**.

```bash
mailbender status                            # resolved url, whether a token is set, reachability
mailbender chat "What did Sarah say?"
mailbender run --type main|style|feedback     # default main
mailbender priorities
mailbender history --limit 50
mailbender audit --limit 50
mailbender categories list|add NAME|remove NAME|seed
mailbender mappings list|add CATEGORY FOLDER|remove CATEGORY
mailbender logout
```

Add `--json` to any command for machine-readable output (JSON to stdout). `--url`/`--token` override config; `--verbose` shows tracebacks.

### Server administration

Server-only operations run inside the container (full stack via the `[server]` extra):

```bash
docker compose exec scheduler mailbender-server scheduler   # the periodic loop (already the scheduler service)
```

Migrations run automatically from the container entrypoint.

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
