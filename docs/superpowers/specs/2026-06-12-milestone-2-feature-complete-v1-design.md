# Design: Milestone 2 — Feature-Complete v1

**Datum:** 2026-06-12
**Status:** Genehmigt (Design)
**Baut auf:** `2026-06-12-email-sorting-agent-design.md` (Milestone 1 — Core)

## Überblick

Milestone 1 lieferte die Kern-Pipeline (classify/prioritize/index/move/draft),
die Lern-Module, einen Chat-Kern, einen dünnen CLI/API-Skeleton und ein
Zwei-Container-Deployment. Dieser Milestone macht mailagent zu einem
**selbst-laufenden Dienst** und legt **jede Kern-Fähigkeit über CLI und API**
offen — damit ist die v1 gegenüber dem Kern-Design funktional vollständig.

Es gibt keine Architektur-Umbauten: Wir bauen auf dem bestehenden modularen
Monolithen auf und folgen den vorhandenen Mustern (`Repository`, `Runner`,
`build_runner`, `create_app` + `require_auth`, `cli/main.py` `_make_*`-Helfer,
`FakeLLMProvider`, Greenmail/Postgres-Testfixtures).

## Anforderungen (aus dem Kern-Design, in diesem Milestone erfüllt)

- **Geplanter/periodischer Hintergrund-Durchlauf** — als eigener Container.
- **Run-Historie** — pro Mail festhalten, welche Schritte gelangen.
- **Fehlerbehandlung** — Retry mit exponentiellem Backoff, Pro-Mail-Isolation.
- **CLI-Vollständigkeit** — `chat`, `history`, `audit`, Prioritäts-Liste,
  Mapping-Verwaltung, manuelle `run-style`/`run-feedback`.
- **Web-API-Vollständigkeit** — Chat, Run-Trigger, Prioritäts-Liste, History,
  Audit, Mapping-CRUD (alles auth-geschützt außer `/health`).
- **Deployment** — Scheduler-Container + Schema-Bootstrap (`alembic upgrade head`).

## Komponenten

### 1. Scheduler-Loop (eigener Container, Cadence pro Run-Typ)

Neue, dünne Datei `src/mailagent/scheduler/loop.py` mit einer testbaren Funktion:

```
run_loop(build_fn, clock, sleep, intervals, *, max_cycles=None)
```

- `clock` und `sleep` werden injiziert → Tests laufen ohne echte Zeit.
- `intervals` = `{"main": minutes, "feedback": minutes, "style": minutes}`.
- Konfiguration erhält `feedback_minutes` (Default 60) und `style_minutes`
  (Default 0 = nur manuell) zusätzlich zum vorhandenen `schedule_minutes` (main).
- Pro Zyklus: für jeden Run-Typ, dessen Intervall seit dem letzten
  `run_history`-Marker abgelaufen ist, den Lauf auslösen; danach einen festen
  Tick (Default 60 s) schlafen. `max_cycles` dient nur dem Test (sonst endlos).
- **„Letzter Lauf"** kommt aus `run_history`: eine Marker-Zeile pro Pass
  (`run_type`, `step="run"`, `result`, `created_at`). Ist `style_minutes=0`,
  feuert der Style-Lauf nie automatisch (Bootstrap bleibt manuell via CLI).
- Neues CLI-Kommando `mailagent scheduler` ruft `run_loop` endlos auf; das ist
  das `command` des Scheduler-Containers.

### 2. Run-Historie-Aufzeichnung

`Runner` schreibt in die bisher ungenutzte Tabelle `run_history`:

- **Pro Pass:** eine Marker-Zeile (`run_type`, `step="run"`, `result`) —
  treibt die Cadence und macht Läufe sichtbar.
- **Pro Mail im Hauptlauf:** je eine Zeile pro Pipeline-Schritt (`classify`,
  `prioritize`, `index`, `move`, `draft`) mit `result` ∈
  {`success`, `error`, `skipped`} und kurzem `detail` (z. B. die gewählte
  Kategorie / Priorität). Das liefert die im Kern-Design geforderte
  Teil-Erfolgs-Sichtbarkeit („welche Schritte je Mail gelangen").
- `Repository` erhält Helfer: `record_run_step(run_type, uid, step, result, detail="")`,
  `last_run_at(run_type) -> datetime | None`, `recent_runs(limit) -> list[RunHistory]`.

### 3. Fehlerbehandlung (Retry + Backoff, Pro-Mail-Isolation)

Neue Datei `src/mailagent/util/retry.py`:

```
retry(fn, *, attempts=3, base_delay=1.0, sleep)  # exponentiell: base_delay * 2**(n-1)
```

`sleep` wird injiziert (Tests ohne echte Wartezeit). Angewandt an:

- IMAP `_connect`/`fetch`/`append`/`move` (transiente Netzfehler).
- LLM-Provider-Aufrufe in classify/prioritize/draft/embed/chat.

Bei erschöpften Versuchen: Das vorhandene `try/except` pro Mail in `run_main`
isoliert den Fehler — der fehlgeschlagene Schritt wird als `error` in
Run-Historie + Audit vermerkt, die Mail bleibt **unverarbeitet** (nächster Pass
versucht erneut), der Lauf läuft mit der nächsten Mail weiter. Ein einzelner
Mail-Fehler bricht nie den ganzen Lauf ab.

### 4. CLI-Oberfläche (`cli/main.py`)

Folgt dem bestehenden `_make_*`-Helfer-Muster:

- `chat "<frage>"` — gibt Antwort + Quell-UIDs/Betreffs aus.
- `history [--limit N]` — jüngste Run-Historie-Zeilen.
- `audit [--limit N]` — jüngste Audit-Log-Zeilen.
- `priorities` — verarbeitete Mails nach Priorität sortiert (high→low),
  Priorität hervorgehoben.
- `add-mapping <kategorie> <ordner>` / `mappings` / `remove-mapping <kategorie>`
  — Folder-Mapping-CRUD (spiegelt die Kategorie-Kommandos).
- `run-style` / `run-feedback` — manuelle Trigger (der Loop feuert diese auch).

### 5. Web-API-Oberfläche (`api/app.py`, `api/routes.py`)

Folgt dem `create_app` + `require_auth` + `routes.py`-Muster (alles
auth-geschützt außer `/health`):

- `POST /chat` `{question}` → `{text, sources:[{uid,subject}]}`.
- `POST /run` → löst einen Hauptlauf aus, gibt eine Zusammenfassung zurück.
- `GET /priorities` → nach Priorität sortierte verarbeitete Mails.
- `GET /history?limit=` und `GET /audit?limit=`.
- `GET/POST/DELETE /mappings` → Folder-Mapping-CRUD.
- `app.state` erhält `runner_factory` und `chat_factory` neben `repo_factory`,
  gleich injiziert (Tests bleiben fakeable).

Reine Daten-Aufbereitung lebt in `routes.py` (wie `list_categories`), damit die
Endpunkte dünn bleiben.

### 6. Deployment

- `docker-compose.yml` erhält einen `scheduler`-Service (gleiches Image,
  `command: mailagent scheduler`, gleiche `env_file`, `depends_on: postgres`).
- **Schema-Bootstrap:** ein Entrypoint-Schritt führt `alembic upgrade head` aus,
  bevor App/Scheduler starten (aktuell legt im Deployment nichts das Schema an —
  eine echte Lücke). Realisiert als kleines `docker-entrypoint.sh`, das beide
  Services teilen.
- `.env.example` erhält `MAILAGENT_FEEDBACK_MINUTES` und `MAILAGENT_STYLE_MINUTES`.

## Datenfluss-Ergänzungen

### Scheduler-Zyklus

1. Lese pro Run-Typ `last_run_at` aus `run_history`.
2. Für jeden Typ mit abgelaufenem Intervall: `build_runner(...)` frisch bauen,
   `run_main` / `run_style` / `run_feedback` aufrufen, Marker-Zeile schreiben.
3. Feste Tick-Pause, dann zurück zu 1. (Im Test via `max_cycles` begrenzt.)

### Hauptlauf mit Run-Historie

Erweitert den Milestone-1-Hauptlauf: jeder Schritt (classify/prioritize/index/
move/draft) wird mit Ergebnis in `run_history` protokolliert; am Ende des Passes
die Marker-Zeile. Audit-Log bleibt wie bisher für schreibende Postfach-Aktionen.

## Fehlerbehandlung

Wie im Kern-Design: Retry mit exponentiellem Backoff für IMAP und LLM,
Pro-Mail-Isolation, Teil-Erfolg in der Run-Historie sichtbar, „verarbeitet"-
Markierung erst nach Erfolg, sodass abgebrochene Läufe nur Unerledigtes
nachholen.

## Teststrategie

Jeder Task ist TDD gegen die vorhandenen Fixtures (`db_session`,
`FakeLLMProvider`, Fake-IMAP, Greenmail). Neue deterministische Nähte:

- `clock`/`sleep` injiziert in `run_loop` und `retry` → keine echte Zeit.
- Fake-`runner_factory`/`chat_factory`/`repo_factory` für API-Tests.
- Loop-Tests nutzen `max_cycles` und einen fixen Fake-Clock, um Cadence-Logik
  (Intervall abgelaufen ja/nein) zu prüfen, ohne zu schlafen.
- Retry-Tests zählen Aufrufe und verifizieren Backoff-Delays über `sleep`-Spy.

Ziel: Die volle Suite bleibt grün und wächst mit jedem Task.

## Bewusst ausgeschlossen (YAGNI für diesen Milestone)

- Browser-Web-Frontend (`web`).
- Realer lokaler LLM-Provider (nur Provider-Abstraktion existiert; openai +
  fake reichen).
- Konfigurierbare Aufbewahrung/Cleanup-Jobs.
- Konfig-Bearbeitung über API/CLI (`config` bleibt ENV-only gemäß
  Sicherheits-Spec).

Diese können spätere Milestones werden.
