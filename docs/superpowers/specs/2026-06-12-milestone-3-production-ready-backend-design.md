# Design: Milestone 3 — Production-Ready Backend

**Datum:** 2026-06-12
**Status:** Genehmigt (Design)
**Baut auf:** `2026-06-12-email-sorting-agent-design.md` (Core) und
`2026-06-12-milestone-2-feature-complete-v1-design.md` (Milestone 2)

## Überblick

Milestone 2 hat die volle CLI/API-Oberfläche und den Scheduler-Container
geliefert, aber drei Lücken offen gelassen, die einen echten Produktivbetrieb
verhindern:

1. Die deployte Web-API **startet nicht** — `create_app(api_token)` ist nicht
   als `uvicorn --factory` aufrufbar, die Factories sind nie verdrahtet, und
   `MAILAGENT_API_TOKEN` ist kein `Config`-Feld.
2. Das **Audit-Log** protokolliert nur `draft_append` und `process_error`,
   nicht die im Sicherheits-Design geforderten Ereignisse.
3. Ein paar **Korrektheits-Lücken** (Duplikat-Draft-Risiko, Retry nur auf
   `_connect`, fehlende Zeitstempel in History/Audit-Ausgabe, Startup-Race
   gegen Postgres).

Dieser Milestone schließt genau diese drei Bereiche. Backend-only, kein UI. Es
folgt den bestehenden Mustern (`Repository`, `Runner`, `build_runner`,
`create_app` + injizierte Factories, `AuditLogger`, `cli/main.py`-Helfer,
Postgres-/GreenMail-Testfixtures). Keine Architektur-Umbauten.

Zusätzlich wird die Anwendung von `mailagent` auf **`mailbender`** umbenannt
(passend zum Repository-Namen). Das ist eine vollständige Umbenennung — Paket,
Imports, CLI-Befehl, ENV-Präfix, DB-Name, Docker und Doku. Da der Dienst noch
nicht produktiv läuft, gibt es keine Rückwärtskompatibilität (keine
`MAILAGENT_*`-Aliase). Die Umbenennung ist der erste Arbeitsschritt, damit alle
weiteren M3-Arbeiten direkt im umbenannten Paket landen.

## Anforderungen (aus Core-Design, in diesem Milestone erfüllt)

- **Web-App-Zugang:** API tatsächlich startbar; Token aus ENV gelesen; Sessions
  pro Request sauber verwaltet (keine Connection-Leaks).
- **Audit-Log:** Auth-Fehlversuche, Konfig-Änderungen (Kategorien/Mappings),
  manuell ausgelöste Läufe, Chat-Anfragen (ohne Inhalt), Postfach-Schreib-
  aktionen (Move + Draft-Append), grobkörnige Provider-Nutzung (pro Lauf/Chat).
- **Audit-Felder:** Zeitstempel pro Eintrag in CLI- und API-Ausgabe sichtbar.
- **Move/Append-Sicherheit:** Retry auf den eigentlichen IMAP-Operationen;
  Idempotenz gegen Duplikat-Drafts bei Wiederholung.
- **Deployment-Robustheit:** App/Scheduler starten erst, wenn Postgres bereit
  ist.

## Komponenten

### 0. Anwendungs-Umbenennung mailagent → mailbender

Vollständige Umbenennung, als erster Schritt des Milestones, damit alles Weitere
im neuen Paket entsteht. Betroffen:

- **Paket:** `src/mailagent/` → `src/mailbender/` (Verzeichnis-Rename inkl. aller
  Untermodule). Alle Imports `mailagent.*` → `mailbender.*` in `src/` und
  `tests/`.
- **Tests:** `tests/`-Importe und Testbaum-Bezüge auf `mailbender` umstellen.
- **pyproject.toml:** `name = "mailbender"`, `[project.scripts] mailbender =
  "mailbender.cli.main:app"`, `pythonpath`/`packages.find` unverändert auf
  `src`. `__version__` bleibt `0.1.0` (in `src/mailbender/__init__.py`).
- **ENV-Präfix:** `MAILAGENT_` → `MAILBENDER_` in `config.py`
  (`SettingsConfigDict(env_prefix="MAILBENDER_")` für `Config` und
  `MAILBENDER_IMAP_` für `ImapConfig`). `.env.example` entsprechend umbenennen.
- **DB-Name:** Default-Datenbank `mailagent` → `mailbender` (in `.env.example`
  `MAILBENDER_DATABASE_URL`, `docker-compose.yml` `POSTGRES_DB`,
  `alembic.ini`-URL). Test-DB `mailagent_test` → `mailbender_test`
  (`tests/conftest.py` `POSTGRES_URL`, `tests/docker-compose.test.yml`).
- **Migrationen:** `migrations/env.py`-Import (`from mailbender.store.models
  import Base`) und das ENV-Lookup auf `MAILBENDER_DATABASE_URL`. Vorhandene
  Migration `migrations/versions/0001_initial.py` ggf. enthaltene
  `mailagent`-Importe umstellen.
- **FastAPI-Titel:** `FastAPI(title="Mailbender")` in `api/app.py`.
- **Docker:** `Dockerfile` `CMD`/`uvicorn`-Pfad auf `mailbender.*`,
  `docker-compose.yml` `command: ["mailbender", "scheduler"]`.
- **Doku:** `README.md` und alle `mailagent`-Erwähnungen → `mailbender`.

**Vorgehen:** Verzeichnis per `git mv` umbenennen (History erhalten), dann
projektweiter Such-/Ersetzlauf `mailagent` → `mailbender` über `src/`, `tests/`
und die Wurzeldateien, danach Neuinstallation (`pip install -e ".[dev]"`) und
volle Test-Suite als Verifikation. Keine `MAILAGENT_*`-Rückwärtskompatibilität.

### 1. API-Produktiv-Bootstrap

**Konfiguration** (`src/mailbender/config.py`): neues Feld
```
api_token: SecretStr | None = None     # MAILAGENT_API_TOKEN
```

**Bootstrap** — neue Datei `src/mailbender/api/bootstrap.py` mit einer
**parameterlosen** `production_app()`-Factory (das ruft `uvicorn --factory` auf):

1. `cfg = load_config()`.
2. Engine via `make_engine(cfg.database_url)`; `SessionLocal =
   scoped_session(sessionmaker(bind=engine, expire_on_commit=False))`.
3. `token = cfg.api_token.get_secret_value() if cfg.api_token else ""`.
4. `app = create_app(api_token=token)`.
5. Factories verdrahten (jede baut ihr Objekt aus einer frischen scoped Session):
   - `app.state.repo_factory = lambda: Repository(SessionLocal())`
   - `app.state.chat_factory = lambda: _build_chat(cfg, SessionLocal())`
   - `app.state.runner_factory = lambda: _build_runner(cfg, SessionLocal())`
     (nutzt `ImapClient` aus `cfg.imap` + `make_provider` + `build_runner`, exakt
     wie der CLI-Helfer `_make_runner`).
6. HTTP-Middleware registrieren, die nach jedem Request `SessionLocal.remove()`
   aufruft (Session-Lifecycle pro Request, kein Leak).
7. `app` zurückgeben.

**Entwurfsentscheidung:** Die Factories bleiben **parameterlos** — alle
bestehenden API-Tests (die `app.state.repo_factory = lambda: FakeRepo()` setzen)
funktionieren unverändert. Das `scoped_session` + Remove-Middleware übernimmt
das Session-Management nur im Produktiv-Pfad. `create_app` bleibt unverändert.

**Deployment** (`Dockerfile`): `CMD` →
`uvicorn mailbender.api.bootstrap:production_app --factory --host 0.0.0.0 --port 8000`.

**Test:** Unit-Test patcht `load_config` und die Engine-Erzeugung und prüft, dass
`production_app()` eine App mit gesetztem `api_token` und nicht-`None` Factories
liefert (ohne echte DB/Server). Die bestehenden `create_app`-Tests bleiben grün.

### 2. Audit-Log-Vervollständigung

`AuditLogger.record(actor, action, target="", result="success")` existiert. Die
geforderten Ereignisse werden an den Call-Sites instrumentiert, die eine Session
besitzen:

| Ereignis | Wo | actor | action | target |
|----------|-----|-------|--------|--------|
| Auth-Fehlversuch (401) | `require_auth` in `api/app.py` | `web` | `auth_failure` | `""` (result=`error`) |
| Kategorie hinzufügen/entfernen | CLI `add-category`/`remove-category` (es gibt keine Kategorie-Mutations-API) | `cli` | `category_add`/`category_remove` | Name |
| Mapping hinzufügen/entfernen | CLI `add-mapping`/`remove-mapping`, API `POST`/`DELETE /mappings` | `cli`/`web` | `mapping_add`/`mapping_remove` | Kategorie |
| Manueller Lauf | CLI `run`/`run-style`/`run-feedback`, API `POST /run` | `cli`/`web` | `run_triggered` | run_type |
| Provider-Nutzung (grob) | `Runner.run_main/style/feedback` (1×/Lauf), Chat-Aufruf (1×) | `scheduler`/`cli`/`web` | `provider_use` | Provider-Klassenname |
| Chat-Anfrage | CLI `chat`, API `POST /chat` | `cli`/`web` | `chat_query` | `""` (kein Inhalt) |
| Mail verschoben | `Runner.run_main`, wenn `moved` | `scheduler` | `mail_moved` | UID |
| Draft abgelegt | bereits vorhanden | `scheduler` | `draft_append` | UID |

**Grobkörnige Provider-Nutzung:** Der `Runner` bekommt den Provider-Namen
(`type(provider).__name__`) bei Konstruktion gemerkt und schreibt **einmal pro
Lauf** einen `provider_use`-Eintrag. Chat-Call-Sites (CLI/API) schreiben einen
`provider_use` pro Anfrage. Damit bleibt das Audit-Log sicherheitsfokussiert;
die Schritt-Details liegen weiterhin in der Run-Historie.

**Auth-Erfolg:** Da es keinen diskreten Login-Endpunkt gibt (Bearer-Token pro
Request), wird **kein** Erfolg-pro-Request geloggt — nur Fehlversuche. Diskrete
Login-Erfolge kommen mit dem Web-Login (M4).

**Serialisierung:** `recent_history` und `recent_audit` (`api/routes.py`) sowie
die CLI-Ausgaben `history`/`audit` ergänzen den **Zeitstempel**
(`created_at`, ISO-8601) pro Eintrag — aktuell fehlt er.

### 3. Korrektheits-Fixes

**Duplikat-Draft-Schutz** (`src/mailbender/pipeline/draft_generator.py`):
`generate` prüft zuerst, ob bereits ein `ReferenceDraft` mit demselben
`source_uid` existiert; falls ja, wird **weder** appended **noch** gespeichert
(idempotent bei Wiederholung). Das schließt den häufigen Wiederholungs-Pfad
(`mark_processed` schlug fehl, `ReferenceDraft` war aber committet). Das schmale
Restfenster (Append ok, anschließender DB-Commit schlägt fehl) wird als für den
Single-User-Betrieb akzeptabel dokumentiert.

**Retry auf IMAP-Operationen** (`src/mailbender/imap/client.py`): Die
eigentlichen `c.move(...)`- und `c.append(...)`-Aufrufe werden in `retry(...)`
gekapselt (bisher nur `_connect`). `fetch_folder` bleibt durch den
retry-gekapselten `_connect` abgedeckt.

**Startup-Reihenfolge** (`docker-compose.yml`): Postgres bekommt einen
`healthcheck` (`pg_isready`); `app` und `scheduler` nutzen
`depends_on: postgres: condition: service_healthy`, damit `alembic upgrade head`
im Entrypoint nicht gegen eine noch nicht bereite DB läuft.

## Datenfluss-Ergänzungen

Keine neuen Abläufe. Bestehende Pfade bekommen Audit-Einträge an den oben
genannten Punkten; der Produktiv-API-Pfad bekommt eine echte Session-Quelle und
Token-Prüfung. Der Hauptlauf bleibt unverändert bis auf den
`provider_use`-Eintrag pro Lauf, den `mail_moved`-Eintrag bei Move und den
Duplikat-Draft-Guard.

## Fehlerbehandlung

Wie Core/M2: Retry mit Backoff (jetzt auch auf move/append), Pro-Mail-Isolation,
Run-Historie für Teil-Erfolg. Audit-Schreibvorgänge dürfen einen Lauf nicht
abbrechen — sie laufen innerhalb der bestehenden Pro-Mail-`try/except`-Isolation
bzw. nach erfolgreicher Aktion.

## Sicherheit

- **Keine Secrets im Audit-Log:** Nur Aktionen/IDs/Provider-Klassennamen,
  niemals Token, API-Keys, Frage- oder Mail-Inhalt. `chat_query` ohne Inhalt.
- **Token nie geloggt:** `api_token` ist `SecretStr`, wird nur zum Vergleich in
  `require_auth` entpackt, nie in Audit/Logs geschrieben.
- **Auth-Fehlversuche sichtbar:** im Audit-Log nachvollziehbar.

## Teststrategie

- **Bootstrap:** Unit-Test mit gepatchtem `load_config`/Engine; prüft gesetzte
  Factories + Token, ohne echte DB.
- **Audit:** gegen echte Postgres-Testinstanz prüfen, dass die jeweiligen
  Aktionen die erwarteten `AuditLog`-Zeilen erzeugen (CLI via monkeypatch der
  `_make_*`-Helfer mit echter Session; API via injizierte Fakes oder echte
  Session; Runner gegen echte Session).
- **Serialisierung:** `recent_audit`/`recent_history` enthalten `created_at`.
- **Duplikat-Draft:** `generate` zweimal aufrufen → nur ein `ReferenceDraft`,
  nur ein Append.
- **Retry move/append:** Fake-IMAPClient, der beim ersten Versuch wirft, dann
  erfolgreich ist; `sleep` injiziert.
- Volle Suite bleibt grün und wächst pro Task.

## Bewusst ausgeschlossen (spätere Milestones)

- **M4:** Browser-Web-Frontend, diskreter Web-Login (Auth-Erfolg-Logging).
- **M5:** Konfigurierbare Aufbewahrung/Cleanup, realer lokaler LLM-Provider,
  Feedback-Matching über `References`/Betreff-Abgleich, Dedup beim
  Style-Bootstrap.
