# `infra/compose` — der lokale Entwicklungs-Stack

Alle Datendienste, die ARGUS braucht, in einem Befehl. Ab Phase 1 gilt die
Regel aus Kapitel 18 des Konzepts dauerhaft: der Stack startet auf einem
frischen Rechner in **unter fünf Minuten** und zeigt sinnvolle Daten. Diese
Eigenschaft wird nie geopfert.

```sh
make up      # Vorabprüfung, starten, warten bis benutzbar, Zustand melden
make seed    # Beispieldaten einspielen und Zusammenspiel nachweisen
make health  # jederzeit: läuft alles, und funktioniert es auch?
```

---

## 1. Systemvoraussetzungen

|                            | Minimum | Empfohlen |
| -------------------------- | ------- | --------- |
| Arbeitsspeicher            | 12 GB   | 16 GB     |
| Freier Plattenplatz        | 20 GB   | 40 GB     |
| Docker Engine              | 24.0    | aktuell   |
| Docker Compose             | v2.20   | aktuell   |
| `vm.max_map_count` (Linux) | 262144  | 262144    |

`make preflight` prüft das alles und sagt bei jedem Punkt, was zu tun ist.
`make up` ruft es automatisch auf und startet gar nicht erst, wenn etwas fehlt.

**Linux:** `vm.max_map_count` muss vor dem ersten Start gesetzt werden, sonst
bricht OpenSearch ab:

```sh
sudo sysctl -w vm.max_map_count=262144                              # sofort
echo 'vm.max_map_count=262144' | sudo tee /etc/sysctl.d/99-opensearch.conf
sudo sysctl --system                                                # dauerhaft
```

**macOS / Windows:** Docker Desktop setzt den Wert in seiner VM selbst. Dort ist
stattdessen die Speicherzuweisung entscheidend: _Settings → Resources →_ mindestens
8 GB, besser 12 GB.

**Weniger als 16 GB?** `make up-core` startet nur Postgres, NATS, Valkey und
MinIO — genug für die ersten Konnektoren, ohne OpenSearch und Observability.

---

## 2. Dienste und Ports

| Dienst              | Host-Port | Wofür                                      | Zugang                        |
| ------------------- | --------- | ------------------------------------------ | ----------------------------- |
| PostgreSQL          | 5432      | Primärspeicher: relational, Geo, Zeitreihe | `make psql`                   |
| ClickHouse HTTP     | 8123      | Analytik, Abfragen und Health              | http://localhost:8123/play    |
| ClickHouse nativ    | 9000      | schnelles Binärprotokoll                   | `make clickhouse`             |
| ClickHouse Metriken | 9363      | Prometheus-Endpunkt                        | http://localhost:9363/metrics |
| NATS                | 4222      | Message Bus                                | `make nats-cli`               |
| NATS Monitoring     | 8222      | Health, JetStream-Zustand                  | http://localhost:8222/jsz     |
| Valkey              | 6379      | Cache, Hot State                           | `redis-cli -p 6379 -a …`      |
| MinIO S3-API        | 9002      | Bronze-Layer, Exporte                      | http://localhost:9002         |
| MinIO Konsole       | 9001      | Weboberfläche                              | http://localhost:9001         |
| OpenSearch          | 9200      | Volltext + Vektor                          | http://localhost:9200         |
| Prometheus          | 9090      | Metriken                                   | http://localhost:9090         |
| Grafana             | 3000      | Dashboards                                 | http://localhost:3000         |

Zugangsdaten stehen in `.env` (aus `.env.example` erzeugt). Alle Ports sind dort
konfigurierbar.

> **Warum MinIO auf 9002 und nicht auf 9000?** Weil dort das native
> ClickHouse-Protokoll liegt. Innerhalb des Docker-Netzes hört MinIO weiterhin
> auf 9000 — nur die Veröffentlichung auf dem Host weicht aus.

---

## 3. Was beim Start passiert

`make up` läuft in vier Schritten:

1. **Vorabprüfung** (`scripts/preflight.sh`) — Ports, Speicher,
   `vm.max_map_count`, `.env`. Bricht mit einer konkreten Handlungsanweisung ab,
   statt den Start scheitern zu lassen.
2. **Start** — `docker compose up -d`. Die Reihenfolge ergibt sich aus
   `depends_on` mit `condition: service_healthy`; kein Dienst startet, bevor
   seine Abhängigkeit wirklich arbeitsfähig ist.
3. **Warten** (`scripts/wait-ready.sh`) — bis jeder dauerhafte Dienst _healthy_
   ist und jeder Init-Container mit Code 0 beendet wurde. Zeitlimit 300 s, mit
   Fortschrittsanzeige und benannten Ursachen beim Überschreiten.
4. **Prüfen** (`scripts/health.sh`) — zwei Ebenen, siehe unten.

Dabei laufen drei Initialisierungen, alle idempotent:

| Init              | Was                                                                                      | Wann                     |
| ----------------- | ---------------------------------------------------------------------------------------- | ------------------------ |
| `init/postgres/`  | Erweiterungen (PostGIS, TimescaleDB, pgvector, pg_trgm, btree_gist), Schema `argus_meta` | nur bei leerer Datenbank |
| `minio-init`      | Buckets `argus-bronze`, `argus-exports`                                                  | bei jedem Start          |
| `opensearch-init` | Index-Templates `argus-events`, `argus-reports`                                          | bei jedem Start          |
| `nats-init`       | Streams `ARGUS_RAW`, `ARGUS_CANON`, `ARGUS_ENRICHED`, `ARGUS_ALERTS`                     | bei jedem Start          |

### Healthchecks sind fachlich, nicht formal

Ein offener Port beweist nichts. Deshalb prüft jeder Healthcheck, ob der Dienst
seine Aufgabe erfüllen kann:

- **PostgreSQL** — beantwortet Abfragen **und** hat alle vier Kernerweiterungen
  geladen. Ein Postgres ohne PostGIS ist für ARGUS kein gesunder Postgres.
- **ClickHouse** — beantwortet SQL **und** die Zieldatenbank existiert.
- **NATS** — `/healthz?js-enabled-only=true`: JetStream ist bereit, nicht nur
  der Server. Ein NATS ohne JetStream sähe auf einem Portcheck gesund aus und
  ließe jeden Konnektor scheitern.
- **OpenSearch** — Clusterstatus mindestens gelb (Einzelknoten hat keine
  Repliken, grün ist unerreichbar).
- **MinIO** — `mc ready local`, also die tatsächliche Bedienbereitschaft.
- **Valkey / Prometheus / Grafana** — `PING`, `/-/healthy`, `/api/health`
  inklusive Datenbankzustand.

`make health` legt darüber eine zweite Ebene: existieren die Erweiterungen, die
Buckets, die Streams und die Templates _wirklich_? Ein Container kann healthy
sein, während seine Initialisierung fehlgeschlagen ist.

---

## 4. Speicherbudget

| Dienst              | Limit              |
| ------------------- | ------------------ |
| PostgreSQL          | 2,0 GB             |
| ClickHouse          | 2,0 GB             |
| OpenSearch          | 2,0 GB (Heap 1 GB) |
| MinIO               | 1,0 GB             |
| Prometheus          | 1,0 GB             |
| NATS                | 0,5 GB             |
| Valkey              | 0,5 GB             |
| Grafana             | 0,5 GB             |
| Init-Container (je) | 0,25 GB            |
| **Summe**           | **10,25 GB**       |

`make validate` prüft diese Summe gegen ein Budget von 12 GB und schlägt fehl,
wenn jemand ein Limit erhöht, ohne den Rest anzupassen. Der Rest bis 16 GB ist
Reserve für Betriebssystem, Container-Laufzeit und die Werkzeuge des Entwicklers.

Alle Limits sind in `.env` einzeln anpassbar.

---

## 5. Troubleshooting

### Port bereits belegt

```
[FEHLER] Port 5432 ist belegt (gebraucht von: PostgreSQL).
```

`make preflight` sagt, welcher Port und welcher Dienst. Zwei Wege:

```sh
ss -ltnp 'sport = :5432'      # Linux: wer hält den Port?
lsof -i :5432                 # macOS
```

Entweder den fremden Dienst beenden — häufig ein lokal installiertes Postgres —
oder in `infra/compose/.env` ausweichen:

```sh
POSTGRES_PORT=15432
```

Die Container untereinander sind davon nicht betroffen; sie sprechen weiter
über die internen Standardports.

### OpenSearch startet nicht: `vm.max_map_count`

```
max virtual memory areas vm.max_map_count [65530] is too low
```

Der häufigste Startfehler auf Linux. Lösung siehe §1. `make preflight` fängt
das ab, bevor der Stack überhaupt startet.

Zweithäufigste Ursache ist zu wenig Speicher: OpenSearch wird vom Kernel
beendet (OOM), das Protokoll bricht mitten im Satz ab.

```sh
docker inspect argus-opensearch-1 | grep OOMKilled
```

Dann `OPENSEARCH_MEM_LIMIT` und `OPENSEARCH_JAVA_OPTS` in `.env` senken —
der Heap sollte etwa die Hälfte des Limits betragen.

### Postgres-Erweiterung nicht verfügbar

```
[FEHLT]   postgis
ARGUS: Pflicht-Erweiterungen fehlen: postgis
```

Der Container startet bewusst **nicht**, statt eine halb funktionsfähige
Datenbank als gesund zu melden. Das Init-Skript druckt die Diagnoseschritte;
kurz gefasst:

```sh
docker compose exec postgres psql -U argus -d argus \
  -c "SELECT name, default_version FROM pg_available_extensions ORDER BY name"
```

**Apache AGE fehlt im Standard-Image** — das ist erwartet und kein Fehler. Es
gibt kein öffentliches Image mit allen fünf Erweiterungen. AGE wird erst für den
Graph-Layer (Kapitel 8.3, Phase 5) gebraucht; bis dahin meldet das Init-Skript
es als „offen" und der Stack läuft. Wer es früher braucht:

```sh
make postgres-age-build
# in infra/compose/.env: POSTGRES_IMAGE=argus/postgres-age:local
make reset && make up
```

### MinIO-Bucket existiert bereits

Kein Fehlerfall. `init/minio/init-buckets.sh` prüft vor dem Anlegen und meldet
bestehende Buckets als `[vorhanden]`. Dasselbe gilt für NATS-Streams und
OpenSearch-Templates: alle Init-Skripte sind idempotent und laufen bei jedem
`make up` erneut.

### Neustart nach unsauberem Beenden

Nach einem Stromausfall, `kill -9` oder einem abgestürzten Docker-Daemon:

```sh
make down    # räumt Container und Netzwerk auf, Daten bleiben
make up
```

Reicht das nicht, weil ein Container im Zustand `restarting` klebt:

```sh
docker compose -f infra/compose/docker-compose.yml \
               -f infra/compose/docker-compose.override.yml down --remove-orphans
make up
```

Bleibt ein Datenverzeichnis beschädigt — typisch bei PostgreSQL nach einem
harten Abbruch mitten in der Initialisierung — hilft nur der Neuaufbau:

```sh
make reset && make up
```

`make reset` löscht **alle** Volumes. Das ist in der Entwicklung die richtige
Antwort und in jeder anderen Umgebung die falsche.

### „Variable is not set"

Eine ältere `.env` kennt eine neu hinzugekommene Variable nicht. `make preflight`
meldet das namentlich. Entweder ergänzen oder `.env` löschen und neu erzeugen
lassen.

### Erster Start dauert länger als fünf Minuten

Das Ziehen der Images ist beim allerersten Mal der größte Posten und hängt an
der Leitung, nicht am Stack. Einmalig vorab:

```sh
make pull
```

Danach greift das Fünf-Minuten-Versprechen für jeden weiteren `make up`.

---

## 6. Image-Versionen

Jedes Image ist auf einen **Digest** festgenagelt; der Tag daneben ist nur
Lesehilfe. Damit startet der Stack auf jedem Rechner mit exakt denselben Bits —
`:latest` würde genau die Klasse von Fehlern erzeugen, die man am Freitagabend
sucht.

```sh
make images-check   # meldet, wo Tag und Digest auseinandergelaufen sind
```

Aktualisiert wird bewusst und in einem eigenen Commit: Digest in
`docker-compose.yml` eintragen, `make up`, `make health`, dann committen.

Für den Lizenzteil des Konzepts (Kapitel 14) relevant: **TimescaleDB** wird in
der Community-Edition (Timescale License, TSL) verwendet, nicht in der
Apache-Variante. Die für ARGUS nötige Kompression und die Continuous Aggregates
(Kapitel 8.1) gibt es nur dort. Selbst hosten ist erlaubt; das Anbieten als
verwalteter Datenbankdienst nicht. Sobald ARGUS über den privaten Gebrauch
hinausgeht, gehört das in das Lizenzregister.

---

## 7. Bewusst nicht enthalten

- **Exporter für Postgres, Valkey, OpenSearch und NATS.** Prometheus fragt nur
  ab, was von sich aus einen Endpunkt anbietet (ClickHouse, MinIO, Grafana,
  Prometheus selbst). Dauerhaft rote Ziele gewöhnen Menschen daran, rote Ziele
  zu ignorieren. Die Exporter kommen mit dem Observability-Ausbau (Prompt 62).
- **OpenSearch Dashboards.** Kostet ein weiteres Gigabyte und rund eine Minute
  Startzeit; die Suche lässt sich per HTTP prüfen.
- **Anwendungsdienste** (`apps/api`, `apps/web`, `services/*`). Dieser Stack
  liefert die Datendienste. Die Anwendungscontainer kommen mit den jeweiligen
  Modulen dazu — dann bekommt `docker-compose.override.yml` auch echtes
  Hot Reload über eingebundene Quellverzeichnisse.
- **TLS und Authentifizierung** bei OpenSearch. Entwicklungsumgebung; in
  staging und prod wird das Sicherheits-Plugin aktiviert (Kapitel 13).
- **Backups.** `make reset` ist hier die richtige Antwort auf einen kaputten
  Zustand. PITR und Wiederherstellungsläufe gehören zu Prompt 68.

---

## 8. Dateien

```
infra/compose/
├─ docker-compose.yml            Dienste, Healthchecks, Limits (auch CI-tauglich)
├─ docker-compose.override.yml   Entwicklungskomfort: Ports, Grafana ohne Login
├─ .env.example                  alle Variablen, kommentiert
├─ config/
│  ├─ prometheus/prometheus.yml
│  ├─ clickhouse/zz-argus.xml            Prometheus-Endpunkt, Speichergrenzen
│  ├─ clickhouse/zz-dev-logging.xml      nur Entwicklung
│  └─ grafana/                           Datenquellen, Dashboards
├─ init/
│  ├─ postgres/                   Erweiterungen, argus_meta
│  ├─ clickhouse/                 Datenbanken
│  ├─ minio/init-buckets.sh
│  ├─ nats/init-streams.sh
│  └─ opensearch/                 Index-Templates
├─ images/postgres-age/           optionales Postgres-Image mit Apache AGE
└─ scripts/
   ├─ preflight.sh                Vorabprüfung
   ├─ wait-ready.sh               warten bis benutzbar
   ├─ health.sh                   Container- und Fachprüfung
   ├─ seed.sh                     Beispieldaten und Rauchtest
   ├─ validate.py                 statische Prüfung ohne Docker-Daemon
   └─ images-check.sh             Digest-Abgleich
```
