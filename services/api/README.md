# `services/api` — Datenbankschema und Migrationen

Das PostgreSQL-Schema von ARGUS als versionierte Alembic-Migrationen. Die
Migrationen sind die **Wahrheitsquelle für das Datenbankschema**; die DDL-Referenz
unter `packages/schemas/sql/` wird daraus erzeugt und nie von Hand gepflegt.

Die Protobuf-Schemas aus `packages/schemas/` bleiben die Wahrheitsquelle für die
*Datenstrukturen auf der Leitung*. Wo die Abbildung auf PostgreSQL bewusst nicht
1:1 ist, steht die Begründung in [ADR 0003](../../docs/adr/0003-datenmodell.md).

---

## Betrieb

```sh
export DATABASE_URL='postgresql://argus:argus@localhost:5432/argus'

make -C ../.. db-upgrade     # auf den aktuellen Stand bringen
make -C ../.. db-test        # Tests gegen eine echte Datenbank
make -C ../.. db-ddl         # DDL-Referenz neu erzeugen
make -C ../.. db-load        # 1 Mio. Testbeobachtungen laden und messen
```

Direkt mit Alembic:

```sh
.venv/bin/alembic upgrade head
.venv/bin/alembic downgrade -1
.venv/bin/alembic history --verbose
.venv/bin/alembic current
```

### Umgebungsvariablen

| Variable | Bedeutung |
|---|---|
| `DATABASE_URL` | Pflicht. `postgresql://…` oder `postgresql+psycopg://…` |
| `ARGUS_TIMESCALE` | `auto` (Standard), `on`, `off` — siehe unten |
| `ARGUS_ALLOW_DESTRUCTIVE_DOWNGRADE` | `1` erlaubt einen Rollback, der befüllte Tabellen löscht |

---

## Die Migrationen

| Nr. | Inhalt |
|---|---|
| `0001` | Erweiterungen, Schema `argus`, 34 Aufzählungstypen, Hilfsfunktionen (Volltextkonfiguration, `updated_at`, bitemporaler Trigger, RLS-Identität) |
| `0002` | `sources`, `entities` (+ Verlauf), `entity_aliases`, `entity_sanctions` |
| `0003` | `events` (+ Verlauf), `event_entities`, `event_links`, `event_contradictions`, `argus.event_as_of()` |
| `0004` | `reports`, Übersetzungen, Erwähnungen, Georeferenzen, Bericht↔Ereignis |
| `0005` | `observations` als Hypertable oder nativ partitioniert, Kompression, Retention |
| `0006` | `tracks`, `track_gaps`, `relations` (+ Verlauf) |
| `0007` | `aois`, `watchlists`, `scores`, `assessments`, `alerts`, `cases`, `data_gaps` |
| `0008` | Rollen, Row-Level Security, Schema-Invarianten |

Jede Migration hat ein funktionierendes `downgrade`. Der Test
`test_each_migration_can_be_stepped_individually` fährt sie einzeln vor und
zurück — das findet Abhängigkeiten, die im Gesamtlauf zufällig funktionieren.

---

## TimescaleDB oder native Partitionierung

`observations` ist in beiden Fällen nach `observed_at` mit Tagesintervall
partitioniert und trägt dieselben Indizes.

| `ARGUS_TIMESCALE` | Verhalten |
|---|---|
| `auto` (Standard) | TimescaleDB benutzen, wenn verfügbar; sonst native Bereichspartitionierung mit Hinweis |
| `on` | TimescaleDB verlangen; fehlt es, Abbruch mit Handlungsanweisung |
| `off` | immer native Partitionierung |

Mit TimescaleDB: `create_hypertable`, Kompression nach 7 Tagen
(`segmentby = entity_id`), Retention nach 90 Tagen — beides als Policy.

Ohne TimescaleDB: tägliche Partitionen plus
`argus.observations_maintenance()`, die Partitionen anlegt, alte löscht und
meldet, wenn die Auffangpartition nicht leer ist. **Keine Kompression** — das
ist der eigentliche Verlust.

Der Grund für die Alternative ist lizenzrechtlich: TimescaleDB steht unter der
Timescale License, nicht unter Apache.

---

## Fehlerfälle mit Handlungsanweisung

Alle vier sind getestet (`tests/test_migrations.py`):

**Fehlende Erweiterung** — `env.py` prüft vor jeder Migration und nennt, was
fehlt, ob es verfügbar wäre und welcher Befehl hilft. Kein Syntaxfehler tief im
DDL.

**Migration auf nicht-leerer Datenbank** — ein bestehendes `argus`-Schema ohne
`alembic_version` bricht ab. Mögliche Auswege werden genannt (`alembic stamp
head`, falsche `DATABASE_URL`, oder `-x force_existing=1`).

**Rollback mit bereits geschriebenen Daten** — `guard_destructive_downgrade`
zählt die betroffenen Tabellen und bricht mit Zeilenzahlen ab, samt
`pg_dump`-Befehl zum Sichern. Mit `ARGUS_ALLOW_DESTRUCTIVE_DOWNGRADE=1`
ausdrücklich erlaubt.

**Zeitzonenfalle** — `argus.assert_no_naive_timestamps()` schlägt fehl, sobald
eine Spalte `timestamp without time zone` ist. Läuft als Teil von Migration 0008
und als Test. Die Sicht `argus.schema_invariants` macht den Zustand jederzeit
abfragbar.

**Doppelte Alias-Zuordnung** — `UNIQUE (id_type, id_value)` auf
`entity_aliases`. Derselbe Bezeichner kann nie auf zwei Entitäten zeigen.

---

## Row-Level Security

Grundgerüst, nicht das fertige Berechtigungsmodell — die feingranulare
Autorisierung nach AOI, Quelle und Klassifikationsstufe läuft später über
OpenFGA. RLS ist die zweite Verteidigungslinie: selbst wenn die Anwendung eine
Prüfung vergisst, gibt die Datenbank nichts heraus.

Die Anwendung setzt je Verbindung:

```sql
SET LOCAL argus.user_id = '01HZ...';
SET LOCAL argus.teams   = 'watchfloor,analysts';
```

Ohne gesetzte `user_id` liefert eine geschützte Tabelle **nichts**. Das ist
Absicht: ein vergessenes `SET` soll leere Ergebnisse liefern, nicht alle Daten.

Geschützt sind `aois`, `watchlists`, `cases`, `assessments` sowie `case_items`
und `case_notes` (erben die Sichtbarkeit ihres Cases). Rollen: `argus_readonly`,
`argus_app`, `argus_admin` (BYPASSRLS).

---

## Bekannte Grenzen

* **Kein ORM-Modell.** Autogenerate ist bewusst aus; es bildet PostGIS-Typen,
  Hypertables, generierte Spalten und Trigger nicht korrekt ab. SQLAlchemy-Modelle
  für die API kommen später und müssen dem DDL folgen, nicht umgekehrt.
* **Verlaufstabellen wachsen unbegrenzt.** Bei viel geänderten Objekten
  verdoppeln sie den Speicherbedarf. Eine Auslagerung nach ClickHouse ist der
  Revisionspunkt in ADR 0003.
* **Enum-Erweiterungen brauchen eine eigene Migration** —
  `ALTER TYPE ... ADD VALUE` ist in PostgreSQL nicht in derselben Transaktion
  benutzbar, in der der Typ entsteht.
* **Retention löscht, aggregiert aber nicht.** Kapitel 14 verlangt „nach 90 Tagen
  aggregiert"; die Aggregate gehören nach ClickHouse und sind nicht Teil dieser
  Migrationen.
* **Die Auffangpartition** (`observations_default`, nur ohne TimescaleDB) nimmt
  Zeitstempel außerhalb der angelegten Tage auf. Nicht leer zu sein ist ein
  Datenqualitätsvorfall; `argus.observations_maintenance()` meldet es.
