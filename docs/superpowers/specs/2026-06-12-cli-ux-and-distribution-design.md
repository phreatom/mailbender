# Design: CLI UX & Distribution — Thin Client

**Datum:** 2026-06-12
**Status:** Genehmigt (Design)
**Baut auf:** `2026-06-12-milestone-3-production-ready-backend-design.md`
(produktivfähiges Backend: startbare API, Token aus ENV, Audit-Log).

## Überblick

Die heutige CLI ist *dick*: jeder Befehl verdrahtet sich seine eigene DB-,
IMAP- und LLM-Verbindung über die `_make_*`-Helfer in `cli/main.py`. Praktisch
lässt sie sich daher nur als `docker compose exec app mailbender …` im Container
betreiben — sie braucht die vollständige Server-Umgebung und alle Secrets dort,
wo sie läuft. Das ist die Reibung, die dieser Milestone beseitigt.

Ziel: eine **richtige, benutzerfreundliche CLI** — ein *dünner* HTTP-Client, der
gegen die selbst-gehostete API spricht (URL + Token), per PyPI installierbar ist
(`uv tool install` / `pipx install`), eine geführte Erstkonfiguration hat
(`mailbender login`) und gepflegte Ausgaben liefert (Rich-Tabellen plus ein
globales `--json` fürs Scripting).

Server-seitige Belange (Migrationen, der Scheduler-Loop) bleiben beim Container.
Sie wandern unter ein separates `mailbender-server`-Konsolenskript, das nur mit
dem `[server]`-Extra funktioniert.

Dies ist ein **eigener Milestone** (CLI & Distribution), kein UI. Er baut auf dem
M3-Backend auf und folgt den bestehenden Mustern (`create_app` + injizierte
Factories, `Depends(require_auth)`, `repo_factory()`/`runner_factory()`,
`AuditLogger`, Typer-App).

## Designentscheidungen (im Brainstorming festgelegt)

- **CLI-Modell:** dünner HTTP-Client gegen die API (kein direkter DB-/IMAP-
  Zugriff im Client).
- **Installation:** PyPI; `uv tool install mailbender` / `pipx install mailbender`.
- **Konfiguration/Auth:** `mailbender login`-Wizard → `~/.config/mailbender/config.toml`
  (chmod 600). Auflösungsreihenfolge **Flag > ENV > Datei**.
- **API-Abdeckung:** API wird erweitert, damit der dünne Client den
  Operator-Alltag vollständig abdeckt (Kategorie-Mutation + `run_type`).
- **Ausgabe:** Rich-Tabellen (human) + globales `--json` (maschinenlesbar).
- **Packaging:** ein Paket, dünne Basis-Deps + `[server]`-Extra für den schweren
  Stack (Variante A).

## Komponenten

### 1. Packaging & Entrypoints

**Zwei Konsolenskripte, ein Paket** (`pyproject.toml`):

```toml
[project.scripts]
mailbender        = "mailbender.cli.main:app"          # dünner Client (Basis-Install)
mailbender-server = "mailbender.server_cli.main:app"   # Server-Ops (braucht [server]-Extra)
```

**Dependency-Split:**

- **Basis** (Laptop-Install): `typer`, `httpx`, `rich`, `tomli-w` (Schreiben der
  Config; `tomllib` ist auf 3.12 stdlib fürs Lesen).
- **`[project.optional-dependencies] server`**: der schwere Stack — `fastapi`,
  `uvicorn`, `sqlalchemy`, `alembic`, `psycopg[binary]`, `pgvector`,
  `imapclient`, `pydantic`, `pydantic-settings`, `openai`.

**Modulgrenze (harte Regel):**

- `src/mailbender/cli/` — dünner Client. Importiert **nur** `mailbender.client.*`
  sowie stdlib/`typer`/`rich`/`httpx`. **Niemals** `store`, `imap`, `api`,
  `scheduler`, `llm`, `pipeline`, `config`.
- `src/mailbender/client/` — neue Heimat für Config-Auflösung, HTTP-Client und
  Rendering (siehe §2/§3).
- `src/mailbender/server_cli/` — neue Heimat für den `scheduler`-Befehl (aus dem
  heutigen `cli/main.py` herausgelöst) und künftige Host-only-Ops.
- **Guard-Test:** importiert `mailbender.cli.main` und stellt sicher, dass danach
  keine Server-Module in `sys.modules` auftauchen (bzw. dass der Import bei
  fehlenden Server-Paketen gelingt). Verhindert, dass der dünne Pfad still wieder
  schwere Deps zieht.

**Docker:** Image installiert `.[server]`; `docker-compose.yml`-Scheduler-Command
wird `["mailbender-server", "scheduler"]`. Migrationen laufen weiter aus dem
Entrypoint (`alembic upgrade head`). Der API-Bootstrap
(`mailbender.api.bootstrap:production_app`) bleibt unverändert.

### 2. Konfiguration, Login & HTTP-Client

**Config-Auflösung** (`mailbender/client/config.py`) — Reihenfolge
**Flag > ENV > Datei**:

- **Datei:** `~/.config/mailbender/config.toml` (respektiert `$XDG_CONFIG_HOME`),
  Felder `url` und `token`.
- **ENV:** `MAILBENDER_API_URL`, `MAILBENDER_API_TOKEN`.
- **Flags:** globale `--url` / `--token` an der Root-App.
- Ein Resolver merged das zu `ClientConfig(url, token)`. Fehlt URL+Token komplett,
  beenden API-Befehle freundlich:
  *„Not logged in — run `mailbender login` (or set MAILBENDER_API_URL/TOKEN).“*

**`mailbender login`** (Wizard):

1. URL abfragen (Default `http://localhost:8000`), Token mit verstecktem Input
   (`hide_input=True`).
2. Verifizieren: `GET /health` (Erreichbarkeit), dann ein authentifizierter Call
   (z. B. `GET /categories`), um den Token zu prüfen (401 → „token rejected, try
   again“).
3. Bei Erfolg `config.toml` mit `chmod 600` schreiben, Speicherort ausgeben.
   `--url`/`--token`-Flags können für nicht-interaktive Einrichtung vorbelegen.
   `--no-verify` als Escape-Hatch fürs Offline-Schreiben.

**Begleitbefehle:** `mailbender logout` (Datei löschen) und `mailbender status`
(aufgelöste URL, Token-*Vorhandensein* — nie den Wert — und Erreichbarkeit der
API).

**HTTP-Client** (`mailbender/client/api.py`):

- Dünner `httpx`-Wrapper aus `ClientConfig`: Basis-URL +
  `Authorization: Bearer <token>`, vernünftiger Timeout, eine typisierte Methode
  pro Endpoint (`chat()`, `run(run_type)`, `priorities()`, `categories_*`,
  `mappings_*`, `history()`, `audit()`).
- **Zentrale Fehlerübersetzung** → saubere Meldung + Exit-Code ≠ 0:
  Connection refused („API unreachable at <url> — is the server running?“), 401
  („unauthorized — run `mailbender login` again“), 404, 5xx (Server-Detail
  zeigen). Kein Stacktrace im Normalbetrieb; `--verbose` schaltet ihn wieder ein.

### 3. Befehlsoberfläche & Ausgabe

**Nach Substantiv gruppierte Sub-Apps** (Typer-Sub-`Typer`s) — ersetzt die flache
`add-category`/`remove-category`/`seed-categories`-Liste:

```
mailbender login | logout | status | version

mailbender chat "frage"                        # POST /chat
mailbender run [--type main|style|feedback]     # default main; POST /run
mailbender priorities                          # GET /priorities
mailbender history [--limit N]                 # GET /history
mailbender audit   [--limit N]                 # GET /audit

mailbender categories list                     # GET /categories
mailbender categories add NAME [--description ...]
mailbender categories remove NAME
mailbender categories seed

mailbender mappings list                       # GET /mappings
mailbender mappings add CATEGORY FOLDER
mailbender mappings remove CATEGORY
```

- `scheduler` ist in dieser CLI **weg** — er lebt unter `mailbender-server` (§1).
- `version` bleibt lokal (kein API-Call); zusätzlich als `--version` an der Root.

**Ausgabe-Schicht** (`mailbender/client/render.py`):

- **Globales `--json`-Flag** (Root-Callback, im Typer-Context abgelegt). Gesetzt,
  gibt jeder Befehl das rohe JSON der API aus (bzw. ein lokales Äquivalent für
  `version`/`status`) und sonst nichts — sauber zum Pipen. JSON immer nach
  stdout; menschliches/Log-Geschwätz nach stderr, damit Pipes sauber bleiben.
- **Human-Modus (default):** Rich-Tabellen — `priorities` mit
  prioritätsgefärbten Zeilen (high=rot, medium=gelb, low=dim); `history`/`audit`
  als Tabellen **inklusive `created_at`-Zeitstempel** (von M3 server-seitig
  ergänzt); `categories`/`mappings` als einfache Tabellen. `chat` rendert die
  Antwort als Rich-Panel/Markdown mit darunterstehender Quellenliste. Mutationen
  drucken eine grüne Bestätigungszeile.
- Respektiert `NO_COLOR` und Nicht-TTY (Rich deaktiviert Styling beim Pipen
  automatisch), sodass `--json` und Nicht-TTY beide saubere Maschinenausgabe
  liefern.

### 4. API-Erweiterungen (Lücke schließen)

Kleine Ergänzungen in `api/app.py` + `api/routes.py`, nach dem bestehenden
`Depends(require_auth)` + `repo_factory()`/`runner_factory()`-Muster. Alle über
den M3-`AuditLogger` auditiert (es sind Konfig-Mutationen / manuelle Läufe —
genau die von M3 geforderten Ereignisse):

| Neuer Endpoint | Route-Fn | Repo/Runner-Call | Audit |
|---|---|---|---|
| `POST /categories` `{name, description?}` | `add_category` | `repo.add_category(...)` | `category_add` |
| `DELETE /categories/{name}` | `remove_category` | `repo.remove_category(...)` → 404 bei Abwesenheit | `category_remove` |
| `POST /categories/seed` | `seed_categories` | `seed_default_categories(repo)` → `{added: N}` | `category_seed` |
| `POST /run` `{run_type?}` | `run_main` → `run` | `run_type` ∈ `main\|style\|feedback`; dispatch zu `runner.run_main/style/feedback`; default `main`; 422 bei ungültigem Wert | `run_triggered` mit run_type |

Hinweise:

- `POST /run` bekommt ein optionales `run_type`-Body-Feld (default `main`);
  bestehende Aufrufer, die nichts posten, funktionieren unverändert —
  rückwärtskompatibel.
- Die Endpoints spiegeln die Repo-Methoden, die die dicke CLI ohnehin aufruft
  (`add_category`, `remove_category`, `seed_default_categories`) — keine neue
  Core-Logik, nur HTTP-Oberfläche + Audit.

### 5. Server-CLI, Docker, Tests & Doku

**`mailbender-server`-CLI** (`server_cli/main.py`): Host-only-Ops, die den vollen
Stack brauchen — vorerst nur `scheduler` (1:1 aus dem heutigen `cli/main.py`
übernommen, inkl. `_make_runner`/`run_loop`-Verdrahtung). Platz für späteres
`migrate`, aber der Entrypoint deckt `alembic upgrade head` bereits ab — daher
jetzt nicht.

**Docker:** `Dockerfile` installiert `.[server]`; `docker-compose.yml`-Scheduler
`command: ["mailbender-server", "scheduler"]`. API-Bootstrap unverändert.

**Doku:** README-Abschnitt „CLI“ neu — `uv tool install mailbender` →
`mailbender login` → Befehlsliste; der alte `docker compose exec mailbender …`-
Block schrumpft zu einer Server-Admin-Notiz. Neue Befehlsgruppierung
dokumentiert.

## Datenfluss

Keine neuen Server-Abläufe. Neuer Client-Pfad: `mailbender <cmd>` → Config
auflösen → `httpx`-Call gegen die API → Antwort rendern (Rich oder JSON). Die
API führt die Aktion mit ihren injizierten Factories aus (wie heute) und schreibt
die Audit-Einträge. Die neuen Endpoints fügen sich in den bestehenden
Request-Pfad ein.

## Fehlerbehandlung

- **Client:** zentrale Übersetzung von `httpx`-Fehlern und HTTP-Status in
  freundliche Meldungen + Exit-Code ≠ 0 (kein Stacktrace ohne `--verbose`).
  Fehlende Config → klare „run `mailbender login`“-Meldung.
- **Server:** wie M3 — Retry mit Backoff, Pro-Mail-Isolation, Run-Historie. Neue
  Endpoints geben saubere HTTP-Fehler zurück (404 fehlende Kategorie/Mapping,
  422 ungültiger `run_type`).

## Sicherheit

- **Token-Handhabung im Client:** Config-Datei `chmod 600`; Token nie in
  Klartext-Ausgaben, Logs oder `status` (nur „gesetzt/nicht gesetzt“). Übertragung
  als `Authorization: Bearer` an die (lokal/HTTPS) gehostete API.
- **Keine Secrets im Audit-Log:** unverändert M3 — nur Aktionen/IDs/Provider-
  Klassennamen.
- **Auth-Fehlversuche:** die neuen Endpoints liegen hinter `require_auth`; 401
  wird wie in M3 als `auth_failure` auditiert.

## Teststrategie

- **Dünner Client:** Unit-Tests mit `httpx.MockTransport` (kein Live-Server) —
  prüfen, dass jeder Befehl Methode/Pfad/Body korrekt trifft und korrekt rendert.
  `--json`-Ausgabe als parsbares JSON asserten.
- **Config-Resolver:** Reihenfolge (`Flag > ENV > Datei`), Fehler bei fehlender
  Config, `login` schreibt `chmod 600`, `logout` entfernt die Datei.
- **Import-Grenze (§1):** Import von `mailbender.cli.main` zieht keine
  Server-Module.
- **Neue API-Endpoints:** wie bestehende Routes getestet (injizierte
  Fake-Repo/Runner), inkl. `run_type`-Dispatch + 422 und geschriebener
  Audit-Zeilen.
- **Bestehende dicke-CLI-Tests:** für verschobene/entfernte Befehle stilllegen
  oder gegen den Client neu schreiben.
- Volle Suite bleibt grün und wächst pro Task.

## Beziehung zu M3 (zu beachten)

M3s Audit-Tabelle ordnet `category_add`/`category_remove` der **CLI** zu. Da die
Kategorie-Mutation nun über die API läuft, landet diese Instrumentierung in den
neuen API-Call-Sites (actor `web`), und die dünne CLI schreibt kein Audit (sie
hat keine DB-Session). Sind die M3-Audit-Arbeiten noch nicht gemergt, sind beide
zum Implementierungszeitpunkt zu versöhnen.

## Bewusst ausgeschlossen (spätere Milestones)

- **Standalone-Binary / Homebrew-Tap** (über `uv tool`/`pipx` hinaus).
- **Web-Frontend & diskreter Web-Login** (M4).
- **Weitere Server-CLI-Ops** (`migrate` etc.) über den heutigen Entrypoint hinaus.
- **`run_type` im Scheduler-Loop ändern** — Scheduler bleibt unverändert.
