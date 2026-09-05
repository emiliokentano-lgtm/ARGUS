# Mitarbeiten an ARGUS

Dieses Dokument beschreibt, wie im Repository gearbeitet wird. Es ist kurz
gehalten und beantwortet drei Fragen: wie richte ich mich ein, wie sieht ein
guter Beitrag aus, und woran wird er gemessen.

---

## 1. Einrichten

```sh
make bootstrap
```

Richtet in einem Durchgang ein: den Python-Workspace (uv), den
TypeScript-Workspace (pnpm), die Go-Module und die Git-Hooks. `make doctor`
sagt vorher, welche Werkzeuge fehlen und wie man sie bekommt.

Danach:

```sh
make lint typecheck test    # alles, was ohne laufende Dienste geht
make up                     # Dev-Stack (Docker)
make db-upgrade             # Datenbankschema anlegen
make test-integration       # Tests gegen die laufenden Dienste
```

`make ci-local` fährt dieselbe Kette wie die Pipeline. Wenn das grün ist, ist
die CI es mit hoher Wahrscheinlichkeit auch.

### Eine Umgebung, nicht fünf

Alles Python läuft aus **einer** virtuellen Umgebung an der Wurzel (`.venv`),
die von `uv` aus `uv.lock` erzeugt wird. Kein Paket bringt seine eigene mit.
Dasselbe für Node: ein pnpm-Workspace, eine `pnpm-lock.yaml`.

Der Grund ist nicht Ordnungsliebe. Getrennte Umgebungen verstecken
Abhängigkeitskonflikte zwischen Paketen bis zu dem Moment, in dem beide im
selben Container landen — und dann sucht jemand einen halben Tag.

---

## 2. Branches

`main` ist immer grün und immer deploybar. Es wird nicht direkt auf `main`
gearbeitet.

| Präfix      | Wofür                         | Beispiel                |
| ----------- | ----------------------------- | ----------------------- |
| `feat/`     | neue Funktion                 | `feat/ais-connector`    |
| `fix/`      | Fehlerbehebung                | `fix/cursor-race`       |
| `docs/`     | nur Dokumentation             | `docs/adr-bus-choice`   |
| `refactor/` | Umbau ohne Verhaltensänderung | `refactor/split-runner` |
| `chore/`    | Werkzeuge, Abhängigkeiten     | `chore/bump-ruff`       |

Kurze Branches, kleine Pull Requests. Ein Pull Request, der eine Woche offen
ist, wird nicht mehr sorgfältig gelesen — er wird durchgewunken.

**Rebase statt Merge** beim Aktualisieren des eigenen Branches. Die Historie
auf `main` bleibt linear und lesbar. Auf einem Branch, an dem jemand anderes
arbeitet, wird **nicht** rebased.

---

## 3. Commits

[Conventional Commits](https://www.conventionalcommits.org/). Der
`commit-msg`-Hook prüft das Format; `make bootstrap` richtet ihn ein.

```
<typ>(<bereich>): <beschreibung>

<rumpf: was und warum, nicht wie>

<fusszeilen>
```

**Typen:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`,
`build`, `ci`, `chore`, `revert`

**Bereich:** das Paket oder Verzeichnis — `connector-sdk`, `schemas`, `db`,
`infra`, `geo`, `ingest-sea`.

**Brechende Änderung:** `!` nach dem Bereich und eine Fußzeile
`BREAKING CHANGE: <was bricht und was zu tun ist>`.

```
feat(connector-sdk): Zwei-Phasen-Cursor gegen Datenverlust

Der Cursor wird jetzt vor dem Publish als 'pending' und erst nach der
bestaetigten Zustellung als 'committed' geschrieben. Ein Absturz dazwischen
wiederholt den Batch; Duplikate faengt der dedupe_key ab.

Verifiziert durch tests/test_crash_recovery.py: echter SIGKILL, Neustart,
kein Datensatz verloren.
```

**Der Rumpf ist der wichtige Teil.** Der Diff zeigt, _was_ geändert wurde;
kein Werkzeug zeigt, _warum_. Betreff höchstens 72 Zeichen, kein Punkt am Ende.

---

## 4. Ein neues Paket anlegen

Ein Verzeichnis unter `packages/` oder `services/` tritt dem Workspace erst
bei, wenn es Code enthält. Leere Platzhalter bleiben draußen — sonst schleppt
der Workspace Pakete mit, die es noch nicht gibt.

**Python:** `pyproject.toml` anlegen, in `[tool.uv.workspace] members` der
Wurzel eintragen, `uv sync --all-packages`. Gehört es zu `packages/`, gilt die
strenge mypy-Konfiguration — dann in den `[[tool.mypy.overrides]]`-Block
aufnehmen und einen `py.typed`-Marker anlegen.

**TypeScript:** `package.json` mit den Skripten `lint`, `typecheck` (und, wenn
vorhanden, `test`, `build`) sowie eine `tsconfig.json`, die von
`tsconfig.base.json` erbt. pnpm und Turborepo finden es dann von selbst.

**Go:** `go.mod` anlegen und in `go.work` unter `use` eintragen. Zusätzlich in
`GO_MODULES` im Makefile — im Workspace-Modus greift `./...` nicht über
Modulgrenzen hinweg.

**Testdateinamen sind repositoryweit eindeutig.** pytest importiert Testdateien
ohne `__init__.py` unter ihrem bloßen Dateinamen; zwei `test_roundtrip.py` in
verschiedenen Paketen ergeben denselben Modulnamen und brechen die Sammlung ab.
Der Fehler tritt erst auf, wenn beide Pakete in _einem_ Lauf gesammelt werden —
wer nur sein eigenes Paket testet, sieht ihn nie. Der Hook
`unique-test-module-names` fängt das ab; der Name sagt am besten, welches Paket
gemeint ist (`test_schema_conformance.py`, nicht `test_roundtrip.py`).

**Die Sprache eines Dienstes ist eine Entscheidung mit Messwert.** Sie wird im
README des Dienstes begründet, zusammen mit der Bedingung, unter der sie
umgekehrt wird. „Go wegen des Durchsatzes" ohne Zahl ist keine Begründung —
siehe `services/ingest-sea/README.md`.

---

## 5. Definition of Done

Aus Kapitel 19 des Konzepts. Ein Beitrag ist fertig, wenn:

1. Das Schema in `packages/schemas` definiert und versioniert ist, falls neue
   Datenstrukturen entstehen.
2. Unit-Tests über 70 % der Logikpfade laufen und ein Integrationstest gegen
   eingefrorene Fixtures existiert.
3. Die Fehlerfälle ausdrücklich behandelt sind: Quelle nicht erreichbar,
   Schema geändert, leere Antwort, Rate-Limit, Zeitsprung.
4. Metriken exportiert werden (Durchsatz, Latenz, Fehlerrate).
5. Die Konfiguration aus Umgebungsvariablen kommt, keine Werte im Code.
6. Ein README im Modulordner steht: Zweck, Betrieb, Abhängigkeiten,
   **bekannte Grenzen**.
7. Bei Datenquellen: Eintrag im Lizenzregister.
8. Bei UI: tastaturbedienbar, Kontrast geprüft, Lade- und Leerzustand
   gestaltet.

---

## 6. Code-Review-Checkliste

Reviewer arbeiten diese Liste ab. Sie ist nach Schwere sortiert: was oben
steht, blockiert; was unten steht, ist ein Hinweis.

### Blockierend

- [ ] **Provenienz erhalten?** Lässt sich jede angezeigte Zahl bis zur
      Rohquelle zurückverfolgen? Wird `raw_ref` gesetzt und weitergereicht?
- [ ] **Unsicherheit sichtbar?** Werden Konfidenz, Alter und Quellengüte
      mitgeführt — oder verschwinden sie unterwegs?
- [ ] **Datenlücken sichtbar statt interpoliert?** Wird ein fehlender Wert als
      fehlend geführt, oder wird stillschweigend etwas eingesetzt?
- [ ] **Zeit korrekt?** Alles in UTC, `timestamptz` statt `timestamp`, Valid
      Time und Transaction Time auseinandergehalten?
- [ ] **Fehlerfälle behandelt?** Nicht nur der glückliche Pfad — was passiert
      bei leerer Antwort, 429, geändertem Schema, Absturz mitten im Batch?
- [ ] **Keine Zugangsdaten im Code**, keine Werte, die in die Umgebung
      gehören.
- [ ] **Tests prüfen Verhalten, nicht Umsetzung.** Ein Test, der nach einem
      Refactoring bricht, ohne dass sich das Verhalten geändert hat, ist ein
      Schuldschein.

### Wichtig

- [ ] Sind die Namen im Code dieselben wie im Konzept? (`Observation`,
      `Event`, `dedupe_key`, `sys_period` — nicht `record`, `item`, `hash`.)
- [ ] Ist die **bekannte Grenze** im README nachgeführt, wenn eine
      dazugekommen ist?
- [ ] Steht im Commit-Rumpf, _warum_ — nicht nur _was_?
- [ ] Braucht die Entscheidung ein ADR? (Faustregel: wenn jemand in einem Jahr
      fragen könnte „warum eigentlich so", dann ja.)
- [ ] Ist der Kommentar im Code dort, wo er etwas erklärt, das der Code nicht
      sagen kann — und nicht dort, wo er den Code wiederholt?

### Hinweis

- [ ] Lässt sich etwas vereinfachen, ohne Verhalten zu verlieren?
- [ ] Gibt es eine vorhandene Funktion, die dasselbe tut?

**Ein Review ist keine Abnahme.** Wer approved, übernimmt Mitverantwortung für
das, was danach in Produktion läuft.

---

## 7. Pipeline

Die CI läuft bei jedem Pull Request und soll unter acht Minuten bleiben. Das
wird nicht durch schnellere Rechner erreicht, sondern durch:

- **Pfadfilter** — ein Pull Request, der nur Python anfasst, fährt weder die
  TypeScript- noch die Go-Kette.
- **Caching** — uv, pnpm, Go-Module, Turborepo und Docker-Schichten. Ein
  Cache-Miss verlangsamt, er bricht nichts.
- **Nebenläufigkeit** — Lint, Typprüfung und Tests laufen parallel.

### Flakige Tests

Integrationstests dürfen wiederholt werden (`--reruns 2`). Jede Wiederholung
erscheint als Annotation im Pull Request und in der Job-Zusammenfassung
(`scripts/flake_report.py`).

**Ein Test, der nur beim zweiten Versuch grün wird, ist ein Befund, kein
Erfolg.** Entweder hat der Test eine Annahme über Zeit oder Reihenfolge, die
nicht hält, oder der geprüfte Code hat sie. Die Wiederholungszahl zu erhöhen
ist keine Antwort.

### Stückliste und Schwachstellen

`syft` erzeugt die SBOM, `grype` prüft sie. **Kritische Funde brechen den
Build**; alles darunter erscheint im Bericht und wird im Review entschieden.
Eine Pipeline, die bei jedem `medium` rot wird, wird binnen zwei Wochen mit
`--ignore` gefahren — dann fängt sie gar nichts mehr.

Lokal nachvollziehbar mit `make sbom`.

---

## 8. Verzeichnisse

Die Struktur folgt Kapitel 16 des Konzepts. Zwei Stellen brauchen eine
Erklärung, weil sie sonst verwirren:

- **`services/api`** enthält ausschließlich das PostgreSQL-Schema und die
  Alembic-Migrationen. Die HTTP-API (REST, WebSocket, GraphQL) kommt später
  unter **`apps/api`**.
- **`packages/schemas`** ist die einzige Wahrheitsquelle für Datenstrukturen.
  `packages/sdk-py` und `packages/sdk-ts` werden daraus **erzeugt** und sind
  nicht eingecheckt.

Jedes noch leere Verzeichnis hat ein README, das sagt, wofür es da ist und
mit welchem Schritt es gefüllt wird.

---

## 9. Architekturentscheidungen

Alles unter `docs/adr/`, fortlaufend nummeriert, Vorlage in
`docs/adr/0000-template.md`, Bestand und Regeln in `docs/adr/README.md`.

Ein ADR wird geschrieben, **bevor** der Code entsteht, nicht danach. Der
wichtigste Abschnitt ist **Verworfene Alternativen** — er beantwortet die
Frage, die in zwei Jahren gestellt wird.

Ein zurückgezogenes ADR bleibt stehen und wird als solches markiert. Die
Historie ist der Punkt.

Jedes ADR nennt **negative** Konsequenzen und **messbare Bedingungen für eine
Revision**. Eine reine Vorteilsliste ist kein ADR, sondern eine Werbebroschüre.
