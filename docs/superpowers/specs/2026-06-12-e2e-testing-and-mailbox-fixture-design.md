# Design: E2E Testing & Synthetic Mailbox Fixture

**Date:** 2026-06-12
**Status:** Approved (Design)
**Relates to:** the existing `pytest-docker` setup (pgvector Postgres + GreenMail
IMAP/SMTP) and the `Runner` pipeline (`scheduler/runner.py`).

## Overview

Today's tests seed mail by **SMTP-sending then `time.sleep(1)` and fetching**, with
a single hardcoded GreenMail user and a `FakeLLMProvider` that returns one fixed
category/priority for *every* email. That is fine for unit tests but cannot
support realistic, deterministic **end-to-end** testing of the agent, nor
**exploratory** testing (a developer loading a realistic mailbox and clicking
around / running the agent).

This milestone adds:

1. A **synthetic mailbox fixture** — a declarative corpus loaded into IMAP via
   `APPEND` (no SMTP, no sleep), covering all three agent passes, used as the
   single source of truth for both e2e and exploratory testing.
2. A **rule-based deterministic LLM provider** — a content-driven "fake brain" so
   pipeline runs produce varied, plausible, repeatable outcomes at zero API cost.
3. A **pipeline e2e suite** — seed a real mailbox, run the agent passes against
   real Postgres, assert outcomes in the DB **and** IMAP folders.
4. An **exploratory seed command** — `mailbender-server seed-fixture`.
5. An **opt-in real-LLM prompt-verification e2e** — the same corpus driven through
   a real (OpenAI-compatible) model to verify the prompts themselves, judged by an
   LLM, gated out of CI by a `real_llm` marker.

## Design decisions (settled in brainstorming)

- **E2E boundary:** **pipeline e2e (IMAP↔DB)** — seed a real mailbox, run the
  passes, assert DB + folder outcomes. No HTTP/browser e2e in this milestone.
- **Fake brain:** **rule-based** — the provider derives answers from email
  content via deterministic rules; the corpus reads like real mail with no
  planted answers. Assertions use the manifest's independently-authored `expect`
  labels, so rule/expectation drift fails the test honestly.
- **Fixture format:** **declarative manifest → IMAP `APPEND`** — exact folder,
  date, and flag control; supports Inbox, Sent, and Drafts.
- **Isolation:** **purge + reseed per test** — a loader exposing `reset()` +
  `load()`, run fresh before each e2e test.
- **Corpus scope:** **one full corpus** covering all three passes
  (main/style/feedback), shared between e2e and an exploratory `seed` command —
  one source of truth.

## Structural choice (settled)

The loader and corpus must be usable by **both** the e2e tests and a
`mailbender-server seed-fixture` command. Because `server_cli` must never import
from `tests/`, the reusable mechanism lives in `src`:

- Loader + rule-based provider in `src/mailbender/…`.
- Corpus manifest as a **repo data file** (`fixtures/mailbox.yaml`).
- Both the seed command and the e2e tests import the loader and read the same
  manifest. No test→src import inversion.

## Components

### 1. Rule-based deterministic provider

`src/mailbender/llm/rule_based.py` — `RuleBasedProvider` implementing the
`LLMProvider` interface (same surface the real and fake providers satisfy):

- **`classify(email, categories)`** — ordered, documented rules over content:
  sender/subject/keyword → category (e.g. `noreply@`/`unsubscribe` → Newsletter;
  `invoice`/`payment` → Finance; `Re:` to a known contact → the reply category).
  Falls back to a default category. Only ever returns a value from `categories`.
- **`prioritize(email)`** — rules: known-VIP sender or "urgent"/"asap" → high;
  `Re:`/direct-to-user → medium; bulk/`noreply` → low.
- **`generate_draft(email, style_examples)`** — deterministic templated reply
  referencing the subject/sender (stable string, no randomness).
- **`embed(text)`** — deterministic hash-seeded 1536-dim vector (same text →
  same vector; similar text → nearby vector), so pgvector retrieval is stable if
  chat is exercised later.
- **`chat(question, context)`** — deterministic answer derived from `context`
  (e.g. echoes the top source), matching the existing fake's "no context → not
  found" behavior.

Registered in `llm/factory.py` as provider **`"rules"`** so it is selectable via
`MAILBENDER_LLM_PROVIDER=rules`. This makes **exploratory runs and e2e share the
exact same brain** — offline, free, deterministic. The existing constant
`FakeLLMProvider` stays for unit tests that want a trivial stub.

> Rules live in one well-commented module with a table at the top mapping
> signal → label, so the corpus author and the rules stay legible together.

### 2. Corpus manifest

`fixtures/mailbox.yaml` — a list of message entries:

```yaml
- from: "newsletter@acme.test"
  to: "me@example.com"
  subject: "Acme Weekly — 5 things"
  body: "...unsubscribe..."
  folder: Inbox            # Inbox | Sent | Drafts (any IMAP folder name)
  date: 2026-06-01T09:00:00
  flags: [\Seen]           # optional IMAP flags
  expect:                  # used by e2e assertions only; NOT read by the provider
    category: Newsletter
    priority: low
    moved_to: "Archive/News"   # null if no mapping
    drafted: false
```

**Coverage (all three passes):**

- **Main pass:** Inbox mail spanning every category and priority, including
  reply-worthy mail (drafts get generated), and at least one entry whose category
  has a folder mapping (so a move is asserted) and one that does not (skip).
- **Style pass:** several **Sent** items so `StyleLearner.bootstrap()` has a real
  corpus.
- **Feedback pass:** a **Drafts** entry plus a later **Sent** reply to the same
  thread, so `FeedbackLearner` has a draft-vs-sent pair to compare.

The `expect` labels are authored independently of the provider's rules. The
manifest is the assertion oracle; the provider is the system under test.

### 3. Loader

`src/mailbender/imap/fixture.py` — `MailboxFixture(imap_conn)`:

- **`load(manifest)`** — for each entry: render a MIME message
  (`email.message.EmailMessage`), ensure the target folder exists (create if
  missing), and `APPEND` it with the entry's fixed **internal date** and flags
  (via `imapclient`'s `append(..., msg_time=...)`). Deterministic UIDs are not
  assumed; tests key off subject/headers.
- **`reset()`** — enumerate every folder, mark all messages `\Deleted`, expunge.
  Provider-agnostic (works on any IMAP server, not just GreenMail). **Safety
  guard:** the seed command only calls `reset()` when `--reset` is passed
  explicitly, so it can never wipe a real mailbox by accident.

The loader is pure mechanism — no pytest, no business logic — so both the seed
command and the test fixture reuse it.

### 4. Exploratory seed command

`mailbender-server seed-fixture [--manifest PATH] [--reset]` (in `server_cli`,
which already owns host-only ops): connects to the configured IMAP, optionally
`reset()`s, then `load()`s the corpus. A developer can then point a mail client
or the (future) web UI at the mailbox and run the agent with
`MAILBENDER_LLM_PROVIDER=rules` for a fully offline, deterministic playground.
README gains a short "Exploratory testing" section.

### 5. Pipeline e2e suite

`tests/e2e/` (own `conftest.py`):

- **`mailbox` fixture** — given the session GreenMail service, build a
  `MailboxFixture`, `reset()` then `load(corpus)` **before each test**. Yields a
  handle for post-run IMAP assertions.
- Compose with the existing transactional **`db_session`** (per-test rollback)
  and a `Runner` wired with the **`RuleBasedProvider`**, the real `ImapClient`
  against GreenMail, seeded categories, and a folder mapping.

**Tests:**

- `run_main` over the corpus → for every Inbox entry assert its `expect` block:
  DB `processed_mail` row has the right `category`/`priority`/`moved`/`drafted`,
  **and** moved mail physically landed in the mapped IMAP folder, **and** a draft
  was appended to Drafts when `drafted: true`.
- `run_style` → `StyleLearner` produced style examples from the Sent items.
- `run_feedback` → the draft-vs-sent pair yields the expected feedback artifact.
- **Per-mail isolation** — a deliberately malformed corpus entry is recorded as
  an error without sinking the rest of the run.
- **Idempotency** — a second `run_main` reprocesses nothing (`is_processed`
  short-circuits).

### 6. Reuse & cleanup

- Migrate `tests/imap/test_client.py`'s SMTP+`sleep` seeding to `APPEND`-based
  seeding via the loader where it improves determinism; keep the transient-failure
  retry unit tests as-is.
- GreenMail stays (supports `APPEND` and multiple folders). No new container; the
  e2e suite reuses the existing `docker-compose.test.yml` services.

### 7. Real-LLM prompt-verification e2e (opt-in)

Sections 1–6 prove the **pipeline** works, but by design the `RuleBasedProvider`
never exercises the actual prompts in `llm/openai_provider.py` (`CLASSIFY_PROMPT`,
`PRIORITY_PROMPT`, `DRAFT_PROMPT`, `CHAT_PROMPT`). Whether those prompts elicit
correct behavior from a *real* model is the one thing the fake brain structurally
cannot test. This section adds a separate, **opt-in** e2e layer that drives a real
LLM to verify the prompts themselves — run deliberately, never on every commit.

It is a confidence/regression check on prompt wording, not a CI gate: real-model
output is non-deterministic, costs tokens, and needs an API key.

#### 7a. Configurable OpenAI-compatible provider

Extend `make_provider` / `OpenAIProvider` to accept a `base_url` so the same code
path drives OpenAI, a local server (Ollama / vLLM / LM Studio), or any
OpenAI-compatible gateway. The OpenAI SDK already supports `base_url`, so this is
a thin thread-through, **not** a new provider integration. The test reads three
environment variables:

- `MAILBENDER_LLM_BASE_URL` — endpoint (optional; defaults to OpenAI's).
- `MAILBENDER_LLM_MODEL` — model id (e.g. `gpt-4o-mini`, a local model name).
- `MAILBENDER_LLM_API_KEY` — API key for the endpoint.

`make_provider("openai", api_key, base_url=…, model=…)` constructs
`OpenAIProvider(client=OpenAI(api_key=…, base_url=…), model=…)`. When `base_url`
is unset the behavior is unchanged from today.

#### 7b. Reuses the existing corpus and loader

No new fixture mechanism. The test seeds GreenMail with the **same**
`fixtures/mailbox.yaml` via `MailboxFixture` (Sections 2–3), then runs the real
`Runner` passes with the **`OpenAIProvider`** swapped in for the
`RuleBasedProvider`, against the same real Postgres + IMAP. Only the brain and the
assertion strategy change.

To bound token cost and flakiness, the suite drives a **small curated subset** of
the corpus — a few *unambiguous* emails per pass (clear-cut category/priority,
one obviously reply-worthy email) — selected by a marker/tag in the manifest or a
hardcoded subject allow-list. It does not run the full corpus through the real
model.

#### 7c. LLM-as-judge assertions, with a structural pre-gate

Real output cannot be byte-compared against `expect` labels. Assertions run in two
stages:

1. **Structural pre-gate (free, deterministic):** category ∈ the allowed set;
   priority ∈ `{high, medium, low}`; draft non-empty and references the email's
   subject. Catches malformed/off-spec output and fails fast **before** spending
   judge tokens.
2. **LLM-as-judge:** a second call (same configurable endpoint) is given the
   email, the model's output, and the manifest's `expect` label, and grades
   whether the output is *reasonable* — returning a structured `{pass, rationale}`
   (forced via a strict prompt / parsed defensively). On failure the assertion
   message surfaces the judge's rationale so a real prompt regression is legible,
   not just a red bar.

The judge handles fuzzy outputs (especially drafts) that exact matching cannot,
at the cost of a second non-deterministic call — acceptable because this layer is
opt-in and diagnostic.

#### 7d. CI gating — `real_llm` marker + auto-skip

Two independent guards, so the test is excluded from normal CI **without any
`.github/workflows/ci.yml` change**:

- **Marker, deselected by default.** Register a `real_llm` marker in
  `pyproject.toml` and set `addopts = -m "not real_llm"`. Plain `pytest` (locally
  and in the existing CI job, which runs `pytest -v`) never collects these tests.
- **Auto-skip without config.** Each test `pytest.skip()`s when
  `MAILBENDER_LLM_MODEL` / `MAILBENDER_LLM_API_KEY` are absent, so even an
  explicit `pytest -m real_llm` degrades gracefully on a machine without
  credentials.

Running it locally is an explicit opt-in:

```bash
MAILBENDER_LLM_MODEL=gpt-4o-mini \
MAILBENDER_LLM_API_KEY=sk-… \
pytest -m real_llm
```

(Optionally add `MAILBENDER_LLM_BASE_URL=…` to target a local or alternative
endpoint.) Because the existing CI never sets these secrets *and* the marker is
deselected, the layer is doubly excluded by default; a future opt-in workflow
(manual/nightly, injecting a key from repo secrets and running `-m real_llm`) can
be added without touching this design.

## Data flow

`corpus YAML → MailboxFixture.load → IMAP APPEND (Inbox/Sent/Drafts) → Runner
pass (RuleBasedProvider + real ImapClient + real Postgres) → assertions over
Repository state + IMAP folder contents`. Exploratory path is identical up to the
Runner, driven by `seed-fixture` + a normal agent run instead of test assertions.

## Error handling / determinism

- **No sleeps:** `APPEND` is synchronous; mail is present the moment `load()`
  returns. Any necessary "service responsive" wait reuses the existing
  `docker_services.wait_until_responsive`.
- **Determinism:** rule-based classification + hash-seeded embeddings + fixed
  internal dates → byte-stable runs. No wall-clock or randomness in the provider.
- **Isolation:** IMAP via `reset()`+`load()` per test; DB via the existing
  transactional rollback fixture.

## Security / safety

- `reset()` is destructive; the seed command requires an explicit `--reset` and
  the e2e fixture only ever targets the disposable GreenMail test service. No real
  mailbox is reachable from the suite.
- No secrets in the corpus; synthetic addresses use `.test` / `example.com`.

## Testing strategy (for this milestone's own code)

- **RuleBasedProvider** unit tests: each rule maps the documented signal to the
  expected label; outputs are stable across repeated calls; `embed` is
  deterministic and dimension-correct.
- **MailboxFixture** tests: `load` places entries in the right folders with the
  right internal dates/flags; `reset` empties all folders; round-trip a small
  manifest against GreenMail.
- **seed-fixture command:** loads without `--reset`; refuses to purge without it;
  honors `--manifest`.
- The full suite stays green; the new e2e tests run under the existing
  `pytest-docker` services.
- **Real-LLM e2e (Section 7):** excluded from the default run and from CI by the
  `real_llm` marker; verified manually by running `pytest -m real_llm` against a
  configured endpoint. The structural pre-gate and the `base_url` thread-through
  get ordinary unit coverage (deterministic, no network) so the non-LLM parts of
  the layer stay green in CI.

## Deliberately excluded (later milestones)

- **API/HTTP e2e** and **browser (Playwright) e2e** — scoped to pipeline e2e here;
  the shared fixture is the foundation those later layers will build on.
- **Recorded real-LLM cassettes** — rejected in favor of the rule-based brain for
  the *default* suite. Live real-LLM prompt verification is **in scope** as an
  opt-in layer (Section 7), gated out of CI by the `real_llm` marker.
- **Performance / load testing.**
- **Web UI exploratory wiring** — the seed command is mail-client/agent oriented;
  pointing the (future) web UI at the seeded mailbox is just configuration.
