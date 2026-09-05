# ingest-sea — AIS über AISStream.io

Maritimer Echtzeit-Konnektor. Liest AIS-Nachrichten über einen dauerhaften
WebSocket, übersetzt sie in `Observation` und `Entity` und veröffentlicht sie
auf zwei getrennten NATS-Subjects.

Erster Konnektor mit echtem Volumen und **Referenzimplementierung für alle
weiteren Streaming-Quellen**: wer eine zweite Stromquelle anbindet, kopiert die
Struktur hier und tauscht `parser.py` und `normalize.py` aus.

---

## Warum Python und nicht Go

Bis Prompt 6 lag hier ein Go-Gerüst mit der Begründung „Durchsatz". Es ist
entfernt, und die Entscheidung wird hier begründet statt verschwiegen.

Das Konnektor-Framework aus Prompt 4 — Cursor-Zweiphasenprotokoll,
Bronze-Archivierung mit lokalem Spool, Circuit Breaker, adaptives
Rate-Limiting, Kill-Switch über NATS, Schema-Drift-Erkennung — existiert in
Python. Es in Go noch einmal zu bauen, um einen Durchsatz zu erreichen, der in
Python bereits erreicht wird, wäre die teure Wahl:

| Messung (ohne Instrumentierung)       |                  Wert |
| ------------------------------------- | --------------------: |
| Übersetzung (Parser + Normalisierung) | ~18.400 Nachrichten/s |
| Gesamtkette bis zur Veröffentlichung  |  ~4.200 Nachrichten/s |
| Ziel der Aufgabenstellung             |   2.000 Nachrichten/s |

Reproduzierbar mit `pytest services/ingest-sea/tests/test_throughput.py -s`.

**Wann das kippt:** wenn die Gesamtkette dauerhaft unter **2.500
Nachrichten/s** fällt (Sicherheitsabstand zum Ziel), oder wenn der
Konnektorprozess mehr als **1 GB** hält. Dann ist Go richtig — und dann ist
zuerst zu klären, ob das Framework mitwandert oder nur dieser Dienst.

`services/ingest-air` bleibt Go: ADS-B liegt eine Größenordnung höher.

---

## Wie es funktioniert

```
AISStream (WebSocket)
        │  stream.py — Verbindung, Abonnement, Wiederverbindung
        ▼
   Warteschlange (deque, hart begrenzt)
        │  connector.fetch() entnimmt einen Stapel
        ▼
   SDK-Runner ── Bronze ── normalize ── publish ── Cursor
                              │
                    ┌─────────┴──────────┐
                    ▼                    ▼
     argus.canon.vessel.position   argus.canon.vessel.static
          Observation                  Entity
```

### Ein Strom in einem Poll-Rahmen

Der SDK-Runner ruft `fetch(cursor)` in einer Schleife auf; ein WebSocket
liefert, wann er will. Die Brücke ist die Warteschlange: ein Hintergrundtask
liest dauerhaft, `fetch()` entnimmt.

Der Gewinn ist die **Stapelsemantik des Runners** — Bronze vor Publish, Cursor
erst nach der Bestätigung. Ein Stromkonnektor, der Nachricht für Nachricht
durchreicht, hat diese Reihenfolge nicht und verliert bei jedem Absturz, was
gerade unterwegs war.

### Zwei Subjects, nicht eines

| Subject                       | Objekt        | Lebensdauer      |
| ----------------------------- | ------------- | ---------------- |
| `argus.canon.vessel.position` | `Observation` | Sekunden–Minuten |
| `argus.canon.vessel.static`   | `Entity`      | Monate–Jahre     |

Der Grund ist nicht Ordnungsliebe: eine Position ist nach fünf Minuten
historisch, ein Schiffsname nach fünf Jahren noch aktuell. Über ein gemeinsames
Subject müsste man entweder Positionen zu lange oder Stammdaten zu kurz
vorhalten.

Die Subjects stehen als **Konstanten** in `config.py`, nicht als
Konfigurationswerte. Eine Trennung, die sich per Umgebungsvariable aufheben
lässt, ist keine. Passt `ARGUS_NATS__SUBJECT_PREFIX` nicht dazu, fällt der
Prozess beim Start um — statt still auf ein anderes Subject zu schreiben und
Erfolg zu melden.

### Der Cursor setzt nicht fort

AISStream hat **kein Replay**. Ein Neustart beginnt beim nächsten gesendeten
Satz; was während der Auszeit gefahren wurde, ist weg. Der Cursor zählt nur mit
(Nachrichten, Verbindungen, Verluste) — für die Lückenanzeige, nicht für die
Wiederaufnahme. Wer hier eine Wiederaufnahme hineinliest, plant einen
Wiederanlauf, den es nicht gibt.

Der Wiederherstellungspfad ist die **Bronze-Schicht** (ADR 0001).

---

## Kennungen: MMSI ist keine ID

Eine MMSI gehört der Funkanlage, nicht dem Rumpf; bei Flaggenwechsel wird sie
neu vergeben. Sie zum Schlüssel zu machen hieße, zwei Schiffe über die Jahre
dieselbe Zeile teilen zu lassen — und sie später nicht mehr trennen zu können
(ADR 0005).

- **`EntityRef.id`** trägt die schema-präfixierte Quellbehauptung:
  `imo:9074729`, wenn die Meldung eine IMO mit gültiger Prüfziffer enthält,
  sonst `mmsi:211331640`. `resolution_status` bleibt `PENDING`,
  `resolved_entity_id` leer. Der Konnektor löst nicht auf und behauptet es nicht.
- **`Entity.identifiers`** führt IMO als `STABLE`, MMSI als `MUTABLE`,
  Rufzeichen als `EPHEMERAL`. Das ist die Eingabe des Resolvers.
- **`Entity.entity_id`** ist **provisorisch** und in
  `attributes.entity_id_is_provisional` als solches markiert. Der Resolver führt
  die Kandidaten über `identifiers` zusammen.

**IMO-Prüfziffer.** AIS-Typ 5 liefert im IMO-Feld häufig 0 oder die MMSI. Beides
scheitert an der Prüfziffer und wird nicht als Kennung übernommen; der Vorgang
bekommt die Marke `invalid_imo_checksum`.

### IDs überleben einen Replay

`obs_id` und `entity_id` sind **deterministisch**: 48 Bit ULID-Zeit aus dem
Beobachtungszeitpunkt, 80 Bit aus einem BLAKE2b-Hash über die stabilen
Identitätsfelder. Dieselbe Rohnachricht ergibt auf jeder Maschine dieselbe ID.

Ohne das wäre eine Wiederherstellung aus Bronze eine Verdopplung statt einer
Wiederherstellung. Der Preis, ausdrücklich benannt: der hintere Teil einer
ARGUS-ULID ist kein Zufall, sondern ein Hash — wer sich auf Unvorhersehbarkeit
verlässt, verlässt sich auf etwas, das hier nicht zugesichert wird.

---

## AIS hat keine Nullwerte

Jede Größe hat einen Sentinelwert **im gültigen Wertebereich**, der „nicht
verfügbar" bedeutet:

| Feld         | Sentinel         | Ergebnis                     |
| ------------ | ---------------- | ---------------------------- |
| Breite       | 91               | kein `geo`-Block             |
| Länge        | 181              | kein `geo`-Block             |
| SOG          | 102,3 (roh 1023) | `sog_kn` fehlt               |
| COG          | 360 (roh 3600)   | `cog_deg` fehlt              |
| True Heading | 511              | `heading_deg` fehlt          |
| Rate of Turn | −128             | `rate_of_turn_deg_min` fehlt |
| Tiefgang     | 0                | `draft_m` fehlt              |

Wer sie nicht abfängt, bekommt eine Flotte vor der Küste Ghanas, Schiffe mit
102 Knoten und einen Bugkurs von 511 Grad. Wer sie auf **0** abbildet, macht es
schlimmer: 0 ist ein gültiger Kurs, eine gültige Fahrt und — vor Westafrika —
eine gültige Position. Aus „unbekannt" wird „präzise bekannt und falsch".

Jede `clean_*`-Funktion in `ais.py` gibt deshalb `None` zurück und nie 0.

**Eine Positionsmeldung ohne Position** wird nicht verworfen: sie wird zu
`OBSERVATION_KIND_STATUS` ohne `geo`-Block, mit der Marke `invalid_position`.
Navigationsstatus und Fahrt sind auch ohne Koordinate etwas wert.

**0/0 (Null Island)** wird ebenfalls verworfen — und der Grund ist nicht die
Unwahrscheinlichkeit, sondern das Schema: `GeoPoint.lat/.lon` sind
proto3-`double` ohne Präsenz. Ein Punkt bei 0/0 ist nach einem
Protobuf-Round-Trip nicht mehr von einer fehlenden Position zu unterscheiden;
die Nachricht änderte ihre Bedeutung unterwegs. Die Marke `null_island` bleibt.
_Wäre in einer künftigen Schema-Revision durch `optional double` zu beheben._

### Nicht jede MMSI ist ein Schiff

Die MMSI kodiert ihre eigene Art in den führenden Ziffern. `99…` ist eine
Navigationshilfe (`ENTITY_TYPE_FACILITY`), `111…` ein Suchflugzeug
(`ENTITY_TYPE_AIRCRAFT`), `00…` eine Küstenstation. Bojen fahren nicht — sie als
Schiffe zu führen verdirbt jeden Detektor, der stillstehende Schiffe sucht.

### Qualitätsmarken

`quality.flags` trägt, was aufgefallen ist, ohne dass etwas verworfen wird:
`invalid_position`, `null_island`, `impossible_speed`, `out_of_order_timestamp`,
`future_timestamp`, `no_source_timestamp`, `dead_reckoned`,
`rate_of_turn_saturated`, `virtual_aton`, `invalid_imo_checksum`,
`manual_position_input`, `positioning_system_inoperative`.

Ein Zeitstempel aus der Zukunft wird **markiert, nicht korrigiert**. Ihn auf
„jetzt" zu ziehen verwandelte den Fehler der Quelle in eine Aussage von ARGUS.

---

## Unterstützte Nachrichtentypen

| AISStream                      | AIS   | Ergibt                     |
| ------------------------------ | ----- | -------------------------- |
| `PositionReport`               | 1/2/3 | Observation                |
| `ShipStaticData`               | 5     | Entity                     |
| `StandardClassBPositionReport` | 18    | Observation                |
| `ExtendedClassBPositionReport` | 19    | Observation **und** Entity |
| `AidsToNavigationReport`       | 21    | Observation und Entity     |
| `StaticDataReport`             | 24    | Entity (Teil A oder B)     |

Andere Typen werden gezählt (`aisstream_unsupported_messages_total`) und
verworfen — **einmal je Typ protokolliert, nicht je Nachricht**. Bei 2.000
Nachrichten/s flutet ein unbekannter Typ sonst das Protokoll und verdeckt die
Fehler, wegen denen man hineinsieht.

Typ 24 kommt in zwei Hälften (A: Name, B: Rufzeichen und Typ). Sie werden
**nicht** zusammengeführt: das wäre Zustandshaltung über Nachrichtengrenzen und
ist Aufgabe des Resolvers.

---

## Fehlerfälle

| Fall                           | Verhalten                                                     |
| ------------------------------ | ------------------------------------------------------------- |
| Abbruch ohne Close-Frame       | Wiederverbindung, Abonnement neu aufgebaut                    |
| Geordneter Close-Frame         | ebenso — kein Grund stehenzubleiben                           |
| Stille auf stehender Leitung   | nach `idle_timeout_s` wie ein Abbruch behandelt               |
| Ungültiger API-Schlüssel       | **Abbruch ohne Wiederholung**, `health()` meldet krank        |
| HTTP 401/403 beim Handschlag   | ebenso                                                        |
| Sonstige Dienstfehlermeldung   | protokolliert, Verbindung bleibt                              |
| Nachricht kein JSON            | übersprungen und gezählt                                      |
| Unbekannter Nachrichtentyp     | gezählt, einmal je Typ protokolliert                          |
| Zeitstempel in der Zukunft     | `TIME_QUALITY_IMPLAUSIBLE` + Marke, Wert unverändert          |
| Zeitstempel unlesbar           | `observed_at` fehlt, `TIME_QUALITY_MISSING`                   |
| Positionssprung                | Marke `impossible_speed`, Beobachtung bleibt                  |
| Dublette nach Wiederverbindung | `dedupe_key` → JetStream `Nats-Msg-Id`                        |
| Rückstau im Publisher          | **ältestes** verworfen, gezählt, protokolliert                |
| Unbrauchbarer Satz im Stapel   | übersprungen, Stapel läuft weiter (Rohdaten liegen in Bronze) |

**Warum der Rückstau das Älteste verwirft.** Den Leser blockieren zu lassen
verlagert den Rückstau nur in die Puffer darunter — aus sichtbarem Verlust
würde ein unsichtbares Speicherleck. Bei einer Live-Quelle ohne Replay ist die
neueste Position eines Schiffes mehr wert als die übernächste alte. Verlust
bleibt Verlust: `aisstream_dropped_messages_total` zählt jede Nachricht
(Prinzip 4 — Lücken zeigen, nicht kaschieren).

**Warum ein falscher Schlüssel den Prozess anhält.** Er wird durch Wiederholen
nicht richtig. Ein Konnektor, der sich im Sekundentakt neu anmeldet, wird zu
Recht gesperrt — Kapitel 14. Rückgabewert `2` unterscheidet den Fall von einem
gewöhnlichen Fehler, damit ein Orchestrator nicht endlos neu startet.

---

## Konfiguration

Alles über Umgebungsvariablen; kein Wert steht im Code.

### AISStream

| Variable                          | Standard                              | Bedeutung                                       |
| --------------------------------- | ------------------------------------- | ----------------------------------------------- |
| `ARGUS_AIS_API_KEY`               | —                                     | **Pflicht.** Ohne ihn startet der Prozess nicht |
| `ARGUS_AIS_URL`                   | `wss://stream.aisstream.io/v0/stream` |                                                 |
| `ARGUS_AIS_BOUNDING_BOXES`        | `[]` (weltweit)                       | JSON: `[[[lat_min,lon_min],[lat_max,lon_max]]]` |
| `ARGUS_AIS_MMSI_FILTER`           | `[]`                                  | JSON-Array oder kommagetrennt                   |
| `ARGUS_AIS_MESSAGE_TYPES`         | alle unterstützten                    | wird gegen den Parser geprüft                   |
| `ARGUS_AIS_IDLE_TIMEOUT_S`        | `60`                                  | Stille, ab der die Leitung als tot gilt         |
| `ARGUS_AIS_QUEUE_SIZE`            | `20000`                               | Warteschlange; darüber wird verworfen           |
| `ARGUS_AIS_MAX_BATCH_SIZE`        | `2000`                                | Nachrichten je Stapel                           |
| `ARGUS_AIS_MAX_BATCH_WAIT_S`      | `1.0`                                 | Wartezeit auf einen Stapel                      |
| `ARGUS_AIS_MAX_IMPLIED_SPEED_KN`  | `100`                                 | Schwelle für `impossible_speed`                 |
| `ARGUS_AIS_POSITION_HISTORY_SIZE` | `100000`                              | MMSI mit gemerkter Position (hart begrenzt)     |
| `ARGUS_AIS_RECONNECT_MAX_DELAY_S` | `30`                                  | Deckel des Backoff                              |

Der Schlüssel ist eine `SecretStr`: er erscheint in keinem Protokoll und in
keinem Fehlerbericht. Ins Repository gehört er nie — Vault, SOPS oder der
Secret-Manager der Plattform.

### Aus dem SDK, mit abweichenden Werten

| Variable                     | Wert                   | Warum                                                        |
| ---------------------------- | ---------------------- | ------------------------------------------------------------ |
| `ARGUS_NATS__SUBJECT_PREFIX` | `argus.canon`          | **Pflicht.** Sonst bricht der Start ab                       |
| `ARGUS_POLL_INTERVAL_S`      | `0`                    | Die Wartezeit liegt in `fetch()`, nicht zwischen den Stapeln |
| `ARGUS_CONNECTOR_ID`         | `ingest-sea-aisstream` |                                                              |
| `ARGUS_SOURCE_ID`            | `aisstream`            |                                                              |
| `ARGUS_BATCH_SIZE`           | —                      | wirkungslos: `ARGUS_AIS_MAX_BATCH_SIZE` gilt                 |

Der Standardwert `ARGUS_POLL_INTERVAL_S=60` ist für abfragende Quellen gedacht.
Bleibt er stehen, legt sich der Konnektor nach jedem Stapel 60 Sekunden
schlafen, während die Warteschlange vollläuft.

---

## Betrieb

```bash
export ARGUS_AIS_API_KEY=...            # niemals ins Repository
export ARGUS_AIS_BOUNDING_BOXES='[[[53.0, 6.0], [56.0, 9.5]]]'   # Deutsche Bucht
export ARGUS_NATS__SUBJECT_PREFIX=argus.canon
export ARGUS_POLL_INTERVAL_S=0
export ARGUS_CURSOR__POSTGRES_DSN=postgresql://argus@localhost/argus

uv run python -m aisstream
```

Rückgabewerte: `0` sauber beendet, `1` Fehler, `2` Konfiguration dauerhaft
unbrauchbar (kein Neustart sinnvoll).

### Metriken

`http://<host>:9100/metrics` — alle SDK-Metriken plus:

| Metrik                                 | Typ       | Wofür                                                      |
| -------------------------------------- | --------- | ---------------------------------------------------------- |
| `ingest_lag_seconds`                   | Histogram | `observed_at` → `ingested_at`; p95 < 10 s                  |
| `aisstream_messages_total`             | Counter   | nach Nachrichtentyp                                        |
| `aisstream_unsupported_messages_total` | Counter   | nach Typ                                                   |
| `aisstream_quality_flags_total`        | Counter   | nach Marke — steigt `impossible_speed`, stimmt etwas nicht |
| `aisstream_dropped_messages_total`     | Counter   | **jeder Schritt ist verlorene Beobachtung**                |
| `aisstream_reconnects_total`           | Counter   |                                                            |
| `aisstream_reconnect_duration_seconds` | Histogram | Verlust → wiederhergestellt                                |
| `aisstream_connected`                  | Gauge     | 0/1                                                        |
| `aisstream_queue_depth`                | Gauge     | steigt sie dauerhaft, ist der Publisher der Engpass        |

`ingest_lag_seconds` ist ein Histogramm, weil das Akzeptanzkriterium ein p95
verlangt; die Gauge `connector_lag_seconds` aus dem SDK hält nur den letzten
Wert. Beide messen dasselbe mit unterschiedlicher Auflösung.

---

## Tests

```bash
pytest services/ingest-sea/tests -q                      # 156 Tests
pytest services/ingest-sea/tests/test_throughput.py -s   # Messwerte
```

Die Durchsatztests überspringen sich selbst, wenn ein Tracer läuft (`--cov`):
unter coverage.py misst ein Durchsatztest den Tracer. Ein still herabgesetzter
Grenzwert wäre schlimmer als ein übersprungener Test — er sähe weiter grün aus.

**Die Fixtures sind nicht vom Live-Feed mitgeschnitten.** Sie sind nach der
dokumentierten Drahtform erzeugt; `aisstream.io` ist aus dieser Umgebung nicht
erreichbar und ein Schlüssel liegt nicht vor. Was das für die Aussagekraft
bedeutet, steht in
[`tests/fixtures/aisstream/README.md`](tests/fixtures/aisstream/README.md).

---

## Was hier nicht passiert

Entity Resolution, Anomalie-Erkennung, Kartendarstellung. Auch nicht:
`DataGap`-Objekte für die Auszeiten — die Lücke wird gezählt und protokolliert,
aber noch nicht als Objekt veröffentlicht.

## Rechtliches

Nur öffentlich gesendete AIS-Daten über die reguläre API von AISStream.io, mit
gültigem Schlüssel, im Rahmen der Nutzungsbedingungen. Kein Scraping, keine
Umgehung von Ratenbegrenzungen, keine nicht-öffentlichen Quellen. Der
`license_id` jeder Nachricht ist `aisstream-tos`.

AIS-Daten von Sportbooten können Personenbezug tragen. Der Konnektor speichert
keine Personendaten und setzt `contains_personal_data` nicht — die
Zweckbindung und die Löschfristen aus Kapitel 14 gelten trotzdem für alles, was
daraus abgeleitet wird.
