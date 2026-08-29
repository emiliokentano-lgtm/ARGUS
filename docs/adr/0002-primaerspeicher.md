# ADR 0002 — PostgreSQL als Primärspeicher, mit benannten Ausnahmen

**Status:** angenommen
**Datum:** 2026-08-29
**Betrifft:** `services/api/migrations/`, `infra/compose/`, ADR 0006

---

## Kontext

ARGUS braucht sechs Dinge gleichzeitig: relationale Stammdaten (Entitäten,
Quellen, Fälle), Zeitreihen (Beobachtungen, Millionen pro Tag), Geometrie
(Punkt-in-Polygon, Umkreis), Volltext (Berichte), Graph (Relationen zwischen
Entitäten) und Vektorähnlichkeit (Deduplizierung von Meldungen).

Was unabhängig von der Wahl gilt:

- Kapitel 15 des Konzepts verlangt ausdrücklich, dass PostgreSQL relationale
  Daten, Geometrie und Zeitreihen in _einem_ System hält.
- Betrieb durch eine Person. Jedes zusätzliche System kostet Backup, Monitoring,
  Versionspflege und eine eigene Ausfallart.
- Kapitel 3.4 verlangt Bitemporalität. Transaktionsgrenzen über mehrere Systeme
  hinweg gibt es nicht — geteilte Speicher heißt: keine konsistenten Korrekturen.
- Erwartetes Volumen Phase 0–4: 10⁸–10⁹ Beobachtungen, nicht 10¹².

---

## Betrachtete Optionen

**A — spezialisierte Systeme je Aufgabe.** ClickHouse für Zeitreihen, Postgres
für Stammdaten, Elasticsearch für Volltext, Neo4j für den Graphen, Qdrant für
Vektoren. _Dafür:_ jedes System ist in seiner Disziplin das beste; unabhängig
skalierbar. _Dagegen:_ fünf Backup-Strategien, fünf Upgrade-Pfade, keine
systemübergreifende Transaktion, jede Abfrage über zwei Domänen wird zu
Anwendungscode, der joins von Hand macht.

**B — Postgres als Alleskönner.** PostGIS (Geometrie), TimescaleDB (Zeitreihen),
pgvector (Ähnlichkeit), `tsvector` (Volltext), Apache AGE (Graph). _Dafür:_ eine
Transaktion, ein Backup, ein Monitoring, ein SQL-Dialekt. _Dagegen:_ siehe
Konsequenzen.

**C — Mischform.** Postgres als Wahrheitsquelle, spezialisierte Systeme
ausschließlich als abgeleitete, jederzeit neu aufbaubare Indizes.

**D — nichts tun**, alles in Postgres ohne Erweiterungen. Scheitert an
Punkt-in-Polygon und an der Partitionierung von 10⁹ Zeilen; verworfen.

---

## Bewertungskriterien

| Kriterium                       | Gewicht | A (spez.) | B (alles) | C (Misch) |
| ------------------------------- | ------- | --------- | --------- | --------- |
| Betriebsaufwand für eine Person | hoch    | −−        | ++        | +         |
| Konsistenz über Domänen hinweg  | hoch    | −−        | ++        | ++        |
| Leistung je Einzeldisziplin     | mittel  | ++        | ∘         | +         |
| Leistung bei 100-fachem Volumen | niedrig | ++        | −         | +         |
| Lizenzklarheit                  | mittel  | +         | ∘         | ∘         |
| Umkehrbarkeit                   | hoch    | −         | +         | +         |

Umkehrbarkeit fällt zugunsten von Postgres aus, weil der Weg _heraus_ leicht
ist: eine Tabelle in ein Spezialsystem zu spiegeln kostet einen Konsumenten. Der
Weg zurück — fünf Systeme in eines zusammenzuführen — kostet eine Migration.

---

## Entscheidung

**Wir benutzen PostgreSQL als Primärspeicher und Wahrheitsquelle** (Option C in
der Ausprägung B: Erweiterungen im Kern, spezialisierte Systeme nur als
ableitbare Indizes).

Zwei Ausnahmen werden hier ausdrücklich zugelassen, nicht stillschweigend:

1. **OpenSearch** hält Volltext _und_ Embeddings. Das weicht von „alles in einem"
   ab: pgvector ist bei Millionen Vektoren mit HNSW deutlich langsamer als eine
   dafür gebaute Engine, und Volltext plus Vektor in derselben Abfrage ist genau
   das, was die Meldungsdeduplizierung braucht. OpenSearch ist jederzeit aus
   Postgres neu aufbaubar und damit kein zweiter Primärspeicher.
2. **ClickHouse** hält Aggregate für Auswertungen über lange Zeiträume. Ebenfalls
   ableitbar.

Die zweitbeste Option ist A. Sie wird nicht gewählt, weil das Konzept
Bitemporalität und erklärbare Scores verlangt: beides braucht Korrekturen, die
über Beobachtung, Bewertung und Ereignis hinweg konsistent sind. Über fünf
Systeme hinweg gibt es dafür keine Transaktion, sondern nur Hoffnung.

---

## Konsequenzen

**Positiv**

- Eine Transaktion umspannt Beobachtung, Bewertung und Ereignis. Bitemporale
  Korrektur ist ein `UPDATE`, kein verteiltes Protokoll.
- Ein Backup (`pg_dump` / WAL) sichert den vollständigen Zustand.
- Gemessen: 1 Mio. Beobachtungen in **38,6 s**, 646 MB, 24-Stunden-Abfrage in
  **0,8 ms** über Bitmap Index Scan.

**Negativ**

- **TimescaleDB steht im Kern unter der TSL, nicht unter Apache 2.0.** Das ist
  eine Lizenzbindung mitten im Primärspeicher. Abgefedert durch
  `ARGUS_TIMESCALE=auto|on|off`: das Schema läuft nachweislich auch mit nativer
  RANGE-Partitionierung. Aufgehoben ist sie damit nicht.
- **Kein öffentliches Image hat alle fünf Erweiterungen.** Apache AGE muss selbst
  gebaut werden (`infra/compose/images/postgres-age/`) — ein eigenes Image, das
  bei jedem Postgres-Minor gepflegt werden will.
- **Ein Knoten ist ein Single Point of Failure für sechs Arbeitslasten.** Ein
  Zeitreihen-Vollscan verlangsamt die Fallbearbeitung. Getrennte Systeme hätten
  dieses Problem nicht.
- **Keine Sharding-Option ohne Citus.** Der Weg über einen Knoten hinaus ist
  nicht offen, sondern ein Projekt.
- **pgvector bleibt zurück**, sobald die Vektorzahl in die Millionen geht — der
  Grund für Ausnahme 1 und zugleich der Beweis, dass „alles in einem" ein Ziel
  ist und kein Naturgesetz.

**Was jetzt anders gemacht werden muss**

- Jede Ableitung nach OpenSearch/ClickHouse muss aus Postgres reproduzierbar
  sein. Ein Datum, das nur dort existiert, ist ein Fehler, kein Feature.
- Ressourcengrenzen pro Arbeitslast (`statement_timeout`, Verbindungspools je
  Dienst), damit eine Auswertung nicht die Erfassung anhält.

---

## Bedingungen für eine Revision

- Über **10⁹ Beobachtungen** in der heißen Partition oder Schreiblast über
  **50.000 Zeilen/s** anhaltend.
- Die p95-Latenz interaktiver Abfragen übersteigt **500 ms**, obwohl Indizes und
  Partitionierung ausgereizt sind.
- Die TimescaleDB-Lizenz ändert sich zuungunsten des Self-Hostings — dann
  dauerhaft auf native Partitionierung wechseln.
- Ein zweiter Knoten wird für Verfügbarkeit gebraucht, nicht für Durchsatz.

---

## Nachweise

- Prompt 3: Migrationen `0001`–`0008` laufen dreimal sauber vorwärts und
  rückwärts; Lasttest 1 Mio. Zeilen in 38,6 s; bitemporale Abfrage liefert genau
  eine korrekte Version.
- Prompt 2: alle Image-Digests gegen die Registry aufgelöst; AGE ist in keinem
  davon enthalten — daher das eigene Dockerfile.
- **Nicht gemessen:** der TimescaleDB-Pfad selbst (im Testumfeld nicht
  installierbar) und der AGE-Image-Bau. Beides ist im Code vorgesehen und
  ungeprüft.
