# Design: E-Mail-Sortier- und Antwort-Agent

**Datum:** 2026-06-12
**Status:** Genehmigt (Design)

## Überblick

Ein selbst-gehosteter Dienst, der ein generisches IMAP/SMTP-Postfach anbindet,
eingehende E-Mails automatisch kategorisiert (und optional in IMAP-Ordner
verschiebt) sowie für antwortbedürftige Mails automatisch Antwort-Entwürfe
erzeugt und als IMAP-Drafts zurückschreibt. Der Schreibstil der Entwürfe wird
aus dem Gesendet-Ordner gelernt und über eine kontinuierliche Feedback-Schleife
(Vergleich von generiertem Entwurf und tatsächlich versendeter Mail)
fortlaufend verbessert.

Die App versendet niemals selbst E-Mails – der Versand bleibt manuell im
gewohnten Mail-Client des Nutzers.

## Anforderungen

- **Mail-Backend:** Generischer IMAP/SMTP-Zugang (Lesen + IMAP-Append für
  Drafts; kein automatischer Versand).
- **Plattform:** Ein gemeinsamer Backend-Dienst mit zwei Frontends – **CLI** und
  **selbst-gehostete Web-App**.
- **KI-Provider:** Abstrahiert. **Cloud-API als Default, konfigurierbar** (auch
  lokales Modell möglich).
- **Sortieren:** Kategorisieren **und** optionales Verschieben in IMAP-Ordner.
- **Kategorien:** Standard-Set als Start, frei erweiter- und anpassbar.
- **Priorisierung:** Zusätzlich zur Kategorie ein Dringlichkeits-Ranking
  (hoch/mittel/niedrig) mit Highlighting in CLI/Web.
- **AI-Chat:** Fragen ans Postfach stellen, Antworten aus indexierten
  Mail-Inhalten (z. B. „Was hat Sarah zum Budget gesagt?").
- **Entwürfe:** Automatische Batch-Entwürfe für die Kategorie „Antwort nötig",
  abgelegt als **IMAP-Draft**.
- **Zeitplan:** Geplanter/periodischer Hintergrund-Durchlauf.
- **Stil:** Wird aus dem Gesendet-Ordner gelernt und per Feedback-Schleife
  kontinuierlich verbessert.
- **Datenhaltung:** PostgreSQL.

## Architektur & Komponenten

Ein Backend-Prozess (modularer Monolith) mit gemeinsamem Core, den CLI und
Web-API teilen. Module mit je einer klaren Aufgabe:

| Modul | Aufgabe | Abhängigkeiten |
|-------|---------|----------------|
| `llm-provider` | Abstraktion über KI-Anbieter (Cloud-Default, lokal konfigurierbar); einheitliches Interface `classify()` / `generateDraft()` | Konfiguration |
| `imap-client` | Mails abrufen, Ordner lesen/schreiben, Drafts via IMAP-Append, Gesendet-Ordner lesen | IMAP-Lib |
| `style-learner` | Beispiele aus „Gesendet" extrahieren, Stil-Profil bauen (Few-Shot-Beispiele) | imap-client, store |
| `feedback-learner` | Draft↔Sent-Deltas auswerten und Stil-Profil kontinuierlich verbessern | imap-client, store |
| `classifier` | Mail → Kategorie (Standard-Set + benutzerdefiniert) via `llm-provider` | llm-provider, store |
| `prioritizer` | Mail → Dringlichkeitsstufe (hoch/mittel/niedrig) via `llm-provider` | llm-provider, store |
| `draft-generator` | Für „Antwort nötig"-Mails Entwurf erzeugen, Stil-Profil einbeziehen | llm-provider, style-learner |
| `mover` | Kategorie → Zielordner-Mapping anwenden (optionales Verschieben) | imap-client, store |
| `chat` | Fragen ans Postfach beantworten via Retrieval auf indexierten Mail-Inhalten + `llm-provider` | llm-provider, store |
| `scheduler` | Periodische Läufe: Hauptlauf, Stil-Lernen, Feedback-Lauf | alle obigen |
| `store` | PostgreSQL: Kategorien, Mappings, Prioritäten, Stil-Beispiele, Run-Historie, verarbeitete Mail-IDs, Referenz-Drafts, indexierte Mail-Inhalte, Audit-Log; mit Schema-Migrationen | PostgreSQL |
| `api` | HTTP-API für die Web-App | core |
| `cli` | Terminal-Befehle (run, list, categories, config, history, audit, chat …) | core |
| `web` | Browser-Frontend (Konfiguration, Kategorien, Prioritäts-Liste, Run-Status, Ergebnisse, Chat) | api |

**Deployment:** Zwei Container per `docker-compose` – der App-Dienst und ein
PostgreSQL-Container. Postgres-Daten auf persistiertem Volume. Config als
Datei/ENV. Connection-String aus der Konfiguration/ENV.

## Datenfluss

### A) Periodischer Hauptlauf (vom `scheduler`)

1. **Fetch** – `imap-client` holt neue Mails (UID noch nicht als „verarbeitet"
   in `store`).
2. **Classify** – `classifier` ruft `llm-provider` auf und bestimmt die
   Kategorie. Ergebnis in `store` protokolliert.
3. **Prioritize** – `prioritizer` bestimmt die Dringlichkeitsstufe
   (hoch/mittel/niedrig); Ergebnis in `store` für die priorisierte Ansicht.
4. **Index** – Mail-Inhalt wird in `store` für den AI-Chat indexiert
   (durchsuchbarer Inhalt + Metadaten).
5. **Move (optional)** – `mover` wendet das Kategorie→Ordner-Mapping an; bei
   definiertem Ziel verschiebt `imap-client` die Mail.
6. **Draft** – bei Kategorie „Antwort nötig" erzeugt `draft-generator` einen
   Entwurf mit dem Stil-Profil als Few-Shot-Kontext.
7. **Append Draft** – `imap-client` legt den Entwurf via IMAP-Append im
   Drafts-Ordner ab (kein Versand). Der generierte Inhalt wird als
   „Referenz-Draft" mit der Quell-Mail-UID in `store` gespeichert.
8. **Record** – `store` markiert die Mail als verarbeitet und schreibt einen
   Eintrag in die Run-Historie (Kategorie, Priorität, ob verschoben, ob Entwurf
   erstellt).

### B) Stil-Lernen (Bootstrap, eigener Zeitplan oder manuell)

1. `style-learner` liest eine Stichprobe aus dem Gesendet-Ordner.
2. Extrahiert repräsentative Beispiele (Anrede, Ton, Signatur, typische
   Formulierungen).
3. Speichert ein Stil-Profil in `store`, das `draft-generator` nutzt.

### C) Manuelle Eingriffe (CLI/Web)

- Lauf jetzt starten, Kategorien/Mappings bearbeiten, Stil-Lernen neu anstoßen,
  Run-Historie und Ergebnisse einsehen, nach Priorität sortierte Liste ansehen,
  Audit-Log durchsuchen.

### C2) AI-Chat übers Postfach (CLI/Web, on demand)

1. Nutzer stellt eine Frage (z. B. „Was hat Sarah zum Budget gesagt?").
2. `chat` führt ein Retrieval über die indexierten Mail-Inhalte in `store` durch
   und wählt die relevanten Mails als Kontext.
3. `llm-provider` formuliert die Antwort aus diesem Kontext; die Quell-Mails
   werden als Referenz mit ausgegeben.
4. Chat-Aufruf wird im Audit-Log erfasst (ohne Mail-Inhalt).

### D) Feedback-Lauf (kontinuierliche Verbesserung, periodisch)

1. **Scan Gesendet** – `feedback-learner` liest neue Mails im Gesendet-Ordner.
2. **Match** – ordnet eine versendete Mail dem passenden Referenz-Draft zu (über
   `In-Reply-To` / `References`-Header bzw. Thread-/Betreff-Abgleich).
3. **Diff** – vergleicht generierten Entwurf mit der tatsächlich versendeten
   Antwort und extrahiert das Delta (Ton, gestrichene/ergänzte Passagen,
   Anrede/Signatur-Korrekturen).
4. **Update Profil** – verdichtet Deltas zu Stil-Signalen und aktualisiert das
   Stil-Profil. Stark editierte Beispiele werden höher gewichtet (klares
   Korrektur-Signal); kaum editierte bestätigen den aktuellen Stil.
5. **Record** – speichert eine Feedback-Metrik pro Paar (z. B. Edit-Distanz) in
   der Historie, sichtbar in CLI/Web.

**Zusammenspiel der Lern-Quellen:** `style-learner` = Bootstrap;
`feedback-learner` = kontinuierliche Verbesserung. Beide schreiben in dasselbe
Stil-Profil, das `draft-generator` als Few-Shot-Kontext nutzt.

**Randfälle:**
- Versendete Mail ohne zugehörigen Draft (manuell verfasst) → nur positives
  Stil-Beispiel, kein Diff.
- Draft erstellt, aber nie versendet/verworfen → optional schwaches
  Negativ-Signal oder ignoriert (konfigurierbar).

**Idempotenz:** Verarbeitete Mail-UIDs in `store` verhindern doppelte
Klassifizierung/Beantwortung – auch bei Abbruch und Neustart.

## Fehlerbehandlung

- **IMAP-Ausfälle/Timeouts:** Retry mit exponentiellem Backoff. Stand bleibt
  dank verarbeiteter UIDs konsistent; nächster Lauf holt nur Unerledigtes nach.
- **LLM-Provider-Fehler:** Retry mit Backoff; danach Mail als
  „unklassifiziert"/„kein Entwurf" markieren und im nächsten Lauf erneut
  versuchen. Ein Provider-Fehler stoppt nie den ganzen Lauf.
- **Pro-Mail-Isolation:** Jede Mail wird einzeln verarbeitet; ein Fehler bei
  einer Mail beeinflusst die anderen nicht.
- **Teil-Erfolg sichtbar:** Run-Historie hält je Mail fest, welche Schritte
  gelangen (classified/prioritized/indexed/moved/drafted).
- **Move/Append-Sicherheit:** „verarbeitet"-Markierung erst nach Bestätigung des
  IMAP-Servers – kein Datenverlust bei Abbruch.
- **Feedback-Matching-Unsicherheit:** Ohne eindeutige Zuordnung wird das Paar
  verworfen statt geraten.
- **Chat-Fehler/leerer Kontext:** Findet `chat` keine relevanten Mails, gibt es
  eine ehrliche „keine passende Information gefunden"-Antwort statt Halluzination.

## Sicherheit

- **Kein automatischer Versand** – die App schreibt nur Drafts; Senden bleibt
  manuell.
- **Credentials:** IMAP-Zugang und LLM-API-Keys nur aus ENV/Secret-Datei,
  **nicht in der DB gespeichert** und **nie geloggt**.
- **Self-hosted by design:** Mail-Inhalte verlassen den Server nur bei gewähltem
  Cloud-LLM – bewusste, konfigurierbare Entscheidung (lokaler Provider möglich).
- **Web-App-Zugang:** Authentifizierung (Single-User-Login/Token). Standardmäßig
  an localhost gebunden; Exposition nur bewusst hinter Reverse-Proxy/TLS.
- **Least Privilege:** Postgres-User nur mit nötigen Rechten; IMAP nur mit
  benötigten Ordnern.
- **Datenminimierung:** Im `store` nur, was für Sortierung/Stil/Idempotenz nötig
  ist; konfigurierbare Aufbewahrungsdauer für Mail-Inhalte/Referenz-Drafts.
- **Audit-Log:** Append-only Tabelle im `store`.
  - **Was wird geloggt:** Login/Auth-Versuche an der Web-App (Erfolg/Fehlschlag),
    Konfigurationsänderungen (Kategorien, Mappings, Provider-Wechsel),
    Postfach-schreibende Aktionen (Move, Draft-Append), Provider-Aufrufe
    (welcher Provider, ohne Mail-Inhalt), manuell ausgelöste Läufe,
    Chat-Anfragen (ohne Frage-/Mail-Inhalt).
  - **Felder je Eintrag:** Zeitstempel, Akteur (CLI/Web-User/Scheduler), Aktion,
    betroffenes Objekt (z. B. Mail-UID, Kategorie), Ergebnis (Erfolg/Fehler).
  - **Keine Geheimnisse/Inhalte:** Niemals Credentials, API-Keys oder
    Mail-Klartext – nur Referenzen/IDs.
  - **Append-only & einsehbar:** Einträge werden nicht überschrieben; in CLI
    (`audit`) und Web-App durchsuchbar/filterbar. Aufbewahrungsdauer
    konfigurierbar.

## Teststrategie

### Unit-Tests (pro Modul, mit Mocks)
- `classifier`: korrekte Kategorie-Zuordnung; unbekannte/leere Antworten →
  „unklassifiziert".
- `prioritizer`: korrekte Dringlichkeitsstufe; Default bei unklarer Antwort.
- `mover`: Mapping korrekt angewandt; kein Ziel = kein Verschieben.
- `draft-generator`: Entwurf inkl. Stil-Profil; Referenz-Draft korrekt verknüpft.
- `chat`: Retrieval wählt relevante Mails; leerer Kontext → „nichts gefunden"
  statt Halluzination; Quellen werden referenziert.
- `style-learner` / `feedback-learner`: Beispiel-Extraktion und
  Draft↔Sent-Matching (inkl. „kein Match → verwerfen").
- `store`: CRUD + Idempotenz gegen eine Test-Postgres-Instanz.

### Integrationstests
- `imap-client` gegen einen echten Test-IMAP-Server (z. B. Greenmail/Dovecot im
  Container): Fetch, Move, Draft-Append, Gesendet-Lesen.
- `scheduler`-Hauptlauf end-to-end mit gemocktem LLM + Test-IMAP.
- Feedback-Lauf: versendete Test-Mail → Referenz-Draft → Stil-Profil aktualisiert.

### Fehler-/Resilienz-Tests
- IMAP-Timeout und LLM-Fehler → Retry/Backoff, Pro-Mail-Isolation, korrekte
  „unverarbeitet"-Markierung.
- Abbruch mitten im Lauf → nächster Lauf holt nur Unerledigtes nach.

### E2E / Smoke
- CLI: `run`, `categories`, `config`, `history`, `audit`, `chat` gegen Test-IMAP
  + Test-Postgres.
- Web-API: Auth, Kategorien bearbeiten, Lauf starten, Prioritäts-Liste abrufen,
  Ergebnisse abrufen, Chat-Anfrage stellen.

**Provider-Abstraktion:** Fake-`llm-provider` für deterministische Tests; reale
Cloud/lokale Provider nur in optionalen, manuell ausgelösten Tests.
