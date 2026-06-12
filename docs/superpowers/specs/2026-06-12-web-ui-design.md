# Design: Web UI (M4) — Two-Mode Self-Hosted Frontend

**Date:** 2026-06-12
**Status:** Approved (Design)
**Builds on:** `2026-06-12-milestone-3-production-ready-backend-design.md` (startable
API, token from ENV, audit log) and `2026-06-12-cli-ux-and-distribution-design.md`,
which explicitly defers the **web frontend & web login to "M4"** — this milestone.

## Overview

mailbender is a single-user, self-hosted email-sorting agent. It already sorts
mail, drafts replies into IMAP, and answers chat queries; the actual email
client stays in the user's normal mail app. Today the only human-facing surfaces
are the CLI (a thin HTTP client) and the JSON API.

This milestone adds a **server-rendered web UI** with two top-level modes the
user switches between:

- **Chat mode** — a rich, multi-turn, persistent analytical conversation over the
  mailbox.
- **Operator mode** — a control/monitoring dashboard over the existing operational
  surface (priorities, runs, audit, categories, mappings, run triggers).

The UI ships **inside the existing app container** as part of the same FastAPI
process — no Node toolchain, no separate service. It reuses the established
injected-factory seam (`repo_factory()` / `runner_factory()` / `chat_factory()`)
and the thin route functions in `api/routes.py`.

## Design decisions (settled in brainstorming)

- **Primary job:** combined **chat assistant + operator dashboard** (not a
  per-message mail-triage surface).
- **Frontend stack:** **server-rendered Jinja2 + HTMX**, served by the same
  FastAPI app. No SPA, no build step.
- **Integration (Approach A):** web routes live in the same app and call the core
  factories **directly** server-side, rendering HTML. No internal HTTP hop, no
  proxying through the JSON API.
- **Auth:** a dedicated **`MAILBENDER_WEB_PASSWORD`**, separate from the API
  token, with a signed **HttpOnly cookie session**. The cookie/CSRF signer is
  keyed off a separate **`MAILBENDER_SECRET_KEY`** (not the password), so rotating
  the password does not invalidate sessions. JSON API bearer auth is untouched.
- **Chat:** **persistent + multi-turn** — conversations saved to the DB, with
  prior turns threaded into the LLM for conversational memory.
- **Live updates:** **HTMX polling** of the Overview status strip + priorities;
  everything else loads on navigation/action.
- **Visual identity:** **Terminal skin** — monospace, near-black background
  (`#0c0f12`), green accent (`#39d98a`), status colors (high `#ff5f56`, med
  `#ffbd2e`, low dimmed).

## Visual & interaction design (settled)

**Shell** — one base template wrapping both modes: a top bar with the mode switch
(`💬 chat` ⇄ `⚙ operator`), an agent-health dot, and logout.

**Chat mode** — **chat bubbles** (right-aligned user, left-aligned agent) in the
monospace skin; a **conversation-list rail** on the left; **sources rendered as
clickable chips** that expand inline to show subject + sender. New-chat and
conversation switching via the rail.

**Operator mode** — left nav: Overview, Priorities, Runs & History, Audit log,
then a CONFIG group (Categories, Mappings). The **Overview** landing has:

- a **status strip** of four tiles: *last run* (type · age · count), *queue*
  (high count + processed-today), *next-run countdown*, and a *trigger run*
  control (main · style · feedback);
- **priorities grouped by HIGH / MED / LOW** with per-group counts.

**Smaller surfaces (defaults accepted):**

- **Login** — a single centered password field on the Terminal skin.
- **Source chip click** — expands inline to subject + sender (data the `/chat`
  flow already returns); opening the full message body is out of scope.
- **Categories / Mappings** — simple inline tables with add/remove plus a
  "seed defaults" button.

## Components

### 1. New package `src/mailbender/web/`

Mounted onto the existing FastAPI app. Layout:

```
src/mailbender/web/
  __init__.py
  session.py          # cookie signer + require_web_session dependency + login/logout
  chat_routes.py      # /login excluded; /app/chat* routes
  operator_routes.py  # /app, /app/priorities, /app/runs, /app/audit, /app/categories, /app/mappings
  mount.py            # mount_web(app): attaches routers, static, templates
  templates/          # Jinja2: base.html, login.html, chat.html, operator/*.html + HTMX partials
  static/             # htmx.min.js (vendored), app.css (Terminal skin)
```

**Module boundary (hard rule, mirroring the CLI spec):** `web` is a server-side
*consumer*, not a new business layer. It imports only core
(`store`, `chat`, `audit`, the `api.routes` thin functions, `config`) plus
stdlib / `fastapi` / `jinja2` / `itsdangerous`. It contains **no** classification,
IMAP, or LLM business logic of its own.

### 2. Auth & session (`web/session.py`)

- New config fields on `Config`: **`web_password: SecretStr | None`**
  (`MAILBENDER_WEB_PASSWORD`) and **`secret_key: SecretStr | None`**
  (`MAILBENDER_SECRET_KEY`) — the latter keys the cookie/CSRF signer. Both
  documented in `.env.example`.
- **Secret key handling:** if `MAILBENDER_SECRET_KEY` is set, the signer uses it
  (stable sessions across restarts/processes). If unset, the app generates a
  random ephemeral key per process and **warns** that sessions will not survive
  restarts and won't be shared across workers — recommend setting it. (Mirrors the
  API-token "unset → warn" pattern.)
- `GET /login` renders the password form; `POST /login` compares with
  `hmac.compare_digest` (constant-time). On success, set a cookie
  `mb_session` — **signed** (itsdangerous `TimestampSigner`, keyed off
  `MAILBENDER_SECRET_KEY`) and flagged **HttpOnly, SameSite=Lax, Path=/**;
  `Secure` when the request is HTTPS. On failure, re-render with an error.
- `require_web_session` dependency: verifies the signed cookie (with a max age);
  on failure **redirects to `/login`** (303). Guards every `/app/**` route.
- `GET /logout` clears the cookie and redirects to `/login`.
- **Audit:** `web_login` on success, `web_login_failure` on a bad password,
  `web_logout` on logout — via the existing `AuditLogger`, actor `web`. Never log
  the password.
- If `MAILBENDER_WEB_PASSWORD` is unset, the web UI **refuses login** (mirrors the
  API's behavior when the token is unset) and the login page shows a clear
  "web password not configured" notice. The JSON API keeps working regardless.

### 3. Chat mode — persistence & multi-turn

The largest net-new backend piece, since today's `Chat.ask` is stateless
single-shot.

**Schema (new Alembic migration):**

```python
class Conversation(Base):
    __tablename__ = "conversation"
    id: int (pk)
    title: str(255)                 # derived from first user message, editable later
    created_at: datetime (server_default now())

class ChatMessage(Base):
    __tablename__ = "chat_message"
    id: int (pk)
    conversation_id: int (FK conversation.id, index)
    role: str(16)                   # "user" | "assistant"
    text: Text
    sources_json: Text default ""   # JSON list of {uid, subject} for assistant msgs
    created_at: datetime (server_default now())
```

**Repository methods** (in the existing `Repository`):
`create_conversation(title)`, `list_conversations()`, `get_conversation(id)`
(with ordered messages), `append_message(conversation_id, role, text, sources)`.

**`Chat.ask` extended for memory** — signature becomes
`ask(question, history: list[tuple[str, str]] = [])`. It still embeds the current
question and does the pgvector retrieval per turn, but now threads prior
`(role, text)` turns into `provider.chat(...)` for conversational context. The
default empty `history` keeps **single-shot callers (CLI, JSON `POST /chat`)
working unchanged — backward compatible.**

> Note: `LLMProvider.chat` currently takes `(question, context)`. It gains an
> optional `history` parameter (default empty) so the prompt can include prior
> turns; `fake` and `openai` providers both updated. Backward compatible.

**Web routes (HTMX):**

| Route | Action |
|---|---|
| `GET /app/chat` | conversation rail + the most recent (or empty) thread |
| `GET /app/chat/{id}` | load a conversation thread |
| `POST /app/chat/new` | create a conversation, redirect to it |
| `POST /app/chat/{id}/message` | append the user bubble, run `Chat.ask` with the thread's history, append + render the assistant bubble (with source chips). HTMX swaps in just the new turn. |

**Audit:** `chat_query` and `provider_use` recorded as in the JSON `/chat`
(actor `web`), without storing the question or any mail content.

### 4. Operator mode — views over the existing surface

All read views reuse the thin functions in `api/routes.py`
(`priorities`, `recent_history`, `recent_audit`, `list_categories`,
`list_mappings`) and the existing `runner` / category+mapping repo methods —
**no new core logic, just HTML rendering + `_audit` on mutations** (actor `web`).

| Route | Renders / does |
|---|---|
| `GET /app` (Overview) | status strip + grouped priorities (HTMX-pollable partials) |
| `GET /app/priorities` | full priorities, grouped HIGH/MED/LOW with counts |
| `GET /app/runs` | run history table incl. `created_at` |
| `GET /app/audit` | audit log table incl. `created_at` |
| `GET /app/categories` + `POST` add / `POST .../delete` / `POST .../seed` | category table + mutations |
| `GET /app/mappings` + `POST` add / `POST .../delete` | mapping table + mutations |
| `POST /app/run` `{run_type}` | dispatch `runner.run_main/style/feedback`; default `main`; audited `run_triggered` |

**Next-run countdown** is computed server-side from the most recent main-run
`created_at` + `MAILBENDER_SCHEDULE_MINUTES` (read from config). If the schedule
is `0` (disabled) or there is no prior run, the tile shows "manual" / "—". No new
scheduler coupling — the web layer just reads config + last-run time.

**Live updates:** the Overview status strip and priorities partials carry
`hx-trigger="every 5s"` (or a small configurable interval) and `hx-get` their own
partial endpoints. Other pages load on navigation; mutations use HTMX
form posts that swap the affected table fragment.

### 5. Bootstrap, Docker & docs

- **`production_app()`** additionally: reads `web_password` and `secret_key`,
  constructs the session/CSRF signer (warning + ephemeral key if `secret_key` is
  unset), and calls `mount_web(app)`. The `chat_factory` already exists.
  The per-request fresh-session pattern (and its documented single-worker
  limitation) is unchanged.
- **Docker:** no new service. The same uvicorn process serves the API, the web
  UI, and static assets. `[server]` extra already pulls FastAPI/uvicorn; add
  `jinja2` and `itsdangerous` to the **server** extra (the thin CLI never imports
  `web`). HTMX is **vendored** as a static file (no CDN dependency, fits
  self-hosted/offline).
- **Docs:** README gains a "Web UI" section — set `MAILBENDER_WEB_PASSWORD`,
  open `http://localhost:8000/login`, the two modes. `.env.example` updated.

## Data flow

`browser → GET /login → POST /login (set signed cookie) → /app...`. Each guarded
request: `require_web_session` verifies the cookie, the route calls the injected
core factory directly (same seam the JSON API uses), renders Jinja2/HTMX, and
records audit entries. Chat additionally reads/writes the new conversation tables
and threads history into the provider. No internal HTTP hop; no new background
processes.

## Error handling

- **Auth:** bad password → re-render login with a message + `web_login_failure`
  audit; expired/invalid cookie → 303 redirect to `/login`; unset web password →
  login disabled with a clear notice.
- **Core errors** surface as the existing route functions already behave (e.g.
  404 on missing category/mapping). Web mutations render an inline error fragment
  rather than a stack trace; the agent-health dot reflects reachability.
- **LLM/chat failures** render an error bubble in the thread; the conversation and
  prior turns are preserved.

## Security

- **Web password** stored only as `SecretStr`; compared in constant time; never
  logged, never rendered, never in audit targets.
- **Cookie** signed with `MAILBENDER_SECRET_KEY` (tamper-evident), HttpOnly (no JS
  access), SameSite=Lax (CSRF mitigation for top-level navigations), Secure under
  HTTPS, with a max age. The signing key is independent of the password, so
  password rotation does not log users out.
- **CSRF on mutations:** POST forms include a signed CSRF token (same
  `MAILBENDER_SECRET_KEY`) tied to the session; verified server-side. (HTMX posts
  include it as a header/hidden field.)
- **No secrets in audit** — unchanged from M3: only actions / IDs / provider class
  names. Chat audit never stores the question or mail content.
- **Separation of credentials:** web access (`MAILBENDER_WEB_PASSWORD`) is distinct
  from API/CLI access (`MAILBENDER_API_TOKEN`); revoking one does not affect the
  other.

## Testing strategy

- **Session/auth:** FastAPI `TestClient` — wrong password rejected + audited;
  correct password sets a signed cookie; guarded `/app/**` redirects to `/login`
  when unauthenticated; logout clears the cookie; unset web password disables
  login. A cookie signed with a different `MAILBENDER_SECRET_KEY` is rejected;
  changing the *password* (same secret key) keeps an existing session valid.
- **Chat persistence + memory:** create conversation → post message → reload shows
  the thread; a **fake provider** asserts prior turns are threaded into
  `provider.chat(...)`; **backward-compat** assert `Chat.ask(question)` (no
  history) still works and the JSON `POST /chat` is unchanged.
- **Operator views:** injected fake repo/runner — priorities render grouped with
  counts; runs/audit tables include `created_at`; category/mapping add/remove/seed
  mutate and re-render; `POST /app/run` dispatches the right `run_type` and writes
  the `run_triggered` audit row.
- **Next-run countdown:** computed value given a last-run time + schedule minutes;
  "manual"/"—" when schedule is `0` or no prior run.
- **CSRF:** a mutation without a valid token is rejected.
- **Module boundary:** importing `mailbender.web.*` does not pull the thin-CLI
  modules, and `mailbender.cli.main` still does not import `web`.
- The full suite stays green and grows per task.

## Deliberately excluded (later milestones)

- **Per-message triage / approve-draft UI** (this is a dashboard, not a triage
  surface).
- **SSE / streaming chat responses** (HTMX polling only for now).
- **Multi-user accounts / roles** (single-user tool).
- **Exposing conversations in the JSON API / CLI** (web-only persistence for now;
  the CLI `chat` stays single-shot).
- **Opening full message bodies from source chips** (subject + sender only).
- **Editing/branching conversations** beyond create/append.

## Relationship to prior milestones

- **M3 (audit):** the new web events (`web_login`, `web_login_failure`,
  `web_logout`, plus the existing `chat_query` / `run_triggered` / config
  mutations now also triggered from the web, actor `web`) use the M3
  `AuditLogger` — exactly the configuration-change / manual-run / auth events M3
  defined.
- **CLI & Distribution spec:** that spec lists "Web-Frontend & diskreter
  Web-Login (M4)" as explicitly deferred — this design fulfills it. The thin CLI's
  module boundary (`cli` never imports server modules) is preserved; `web` lives
  on the server side under the `[server]` extra.
