# ARGUS

Selbst gehostete Echtzeit-Lageplattform. Sie sammelt öffentlich verfügbare
Daten aus Luftfahrt, Seefahrt, Nachrichten, Wirtschaft, Politik, Umwelt und
Infrastruktur, normalisiert sie, verknüpft sie miteinander, **priorisiert sie
nachvollziehbar** und stellt sie in einem karten- und zeitachsenzentrierten
War Room dar.

Der Kern ist nicht die Karte. Der Kern ist die Priorisierung: aus Millionen
Rohsignalen pro Tag die zwanzig herauszufiltern, die heute zählen — mit einer
Begründung, die man aufklappen kann.

Drei Sätze, die das Produkt definieren:

1. **Alles ist eine Beobachtung über eine Entität zu einem Zeitpunkt an einem
   Ort.** Ein Datenmodell für Flugzeug, Erdbeben und Zinsentscheid.
2. **Jede Beobachtung bekommt einen Score, und jeder Score ist erklärbar.**
   Priorisierung statt Feed.
3. **Der Nutzer kann jederzeit in der Zeit zurückspringen.** Bitemporale
   Speicherung: was wussten wir wann, nicht nur was wissen wir heute.

---

## Anfangen

```sh
make bootstrap    # Python, TypeScript, Go, Git-Hooks — auf einem frischen Rechner
make lint test    # alles, was ohne laufende Dienste geht
make up           # Dev-Stack: Postgres, ClickHouse, NATS, Valkey, MinIO, OpenSearch, Grafana
make db-upgrade   # Datenbankschema anlegen
make seed         # Beispieldaten und Ende-zu-Ende-Rauchtest
```

`make help` listet alle Ziele. `make doctor` sagt, welche Werkzeuge fehlen.

**Systemvoraussetzungen:** 16 GB Arbeitsspeicher (12 GB Minimum), 20 GB Platte,
Docker, Node 22, Go 1.24, Python 3.11, uv, pnpm. Details und
Troubleshooting in [`infra/compose/README.md`](infra/compose/README.md).

---

## Stand

| Bereich                                     | Zustand                                        |
| ------------------------------------------- | ---------------------------------------------- |
| Kanonische Schemas (Protobuf + JSON Schema) | vollständig, 155 Tests                         |
| Dev-Stack (Docker Compose)                  | vollständig, statisch geprüft                  |
| PostgreSQL-Schema und Migrationen           | vollständig, 35 Tests, 1 Mio. Zeilen in 38,6 s |
| Konnektor-Framework                         | vollständig, 216 Tests, 91 % Abdeckung         |
| Monorepo und CI                             | vollständig                                    |
| Datenquellen, Anreicherung, Scoring, UI     | noch nicht begonnen                            |

Die Roadmap steht in Kapitel 18 des Konzepts. Jedes noch leere Verzeichnis hat
ein README, das sagt, wofür es da ist und mit welchem Schritt es gefüllt wird.

---

## Aufbau

```
apps/            web (War Room) · api (REST/WS/GraphQL) · bot
services/        api (DB-Schema, Migrationen) · ingest-sea (AIS) · ingest-air (ADS-B)
packages/        schemas (Wahrheitsquelle) · connector-sdk · geo · go-runtime · ui-kit
infra/compose/   Dev-Stack
docs/adr/        Architekturentscheidungen
```

Drei Sprachen, drei Werkzeugketten, ein Repository:

- **Python** (uv-Workspace, eine `.venv` an der Wurzel) — Konnektoren,
  Anreicherung, Migrationen, Werkzeuge.
- **TypeScript** (pnpm-Workspace, Turborepo) — Frontend und geteilte Pakete.
- **Go** (go.work) — Hochlast-Ingest, wo das Speicherverhalten zählt. Welcher
  Dienst welche Sprache bekommt, wird gemessen und nicht angenommen:
  `services/ingest-sea` ist Python, weil die Messung es hergibt (Begründung und
  Umkehrbedingung in dessen README).

`packages/schemas` ist die **einzige Wahrheitsquelle** für Datenstrukturen.
Alle Sprachen erzeugen ihre Typen daraus; es gibt keine handgeschriebene
Kopie.

---

## Prinzipien

Sie stehen hier, weil sie Entscheidungen im Code bestimmen und nicht nur im
Konzept:

1. **Provenienz vor Bequemlichkeit** — jede angezeigte Zahl ist bis zur
   Rohquelle rückverfolgbar.
2. **Unsicherheit ist ein First-Class-Attribut** — Konfidenz, Alter und
   Quellengüte sind immer sichtbar.
3. **Erklärbare Scores** — kein Blackbox-Ranking.
4. **Graceful Degradation** — fällt eine Quelle aus, wird das angezeigt, nicht
   stillschweigend interpoliert.
5. **Ereignisse sind unveränderlich** — Korrekturen erzeugen neue Versionen.
6. **Nur öffentlich zugängliche Daten**, keine Überwachung von Privatpersonen,
   keine Umgehung von Nutzungsbedingungen.

Mehrere davon sind nicht nur dokumentiert, sondern erzwungen: die Datenbank
lehnt einen abgeleiteten Ortspunkt ab, der nicht als solcher markiert ist, und
ein Modell-Assessment ohne Beleg.

---

## Mitarbeiten

[`CONTRIBUTING.md`](CONTRIBUTING.md) — Einrichtung, Commit-Format,
Branch-Strategie, Review-Checkliste, Definition of Done.
