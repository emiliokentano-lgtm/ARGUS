# `packages/connector-sdk` — Konnektor-Framework

Gemeinsame Grundlage aller Datenquellen. Ziel aus Kapitel 5 des Konzepts:
**eine neue Quelle anzubinden darf höchstens einen halben Tag kosten.**

Ein Konnektor beschreibt nur noch, _wie_ er Daten holt und in das kanonische
Schema übersetzt. Alles andere kommt von hier: Cursor-Persistenz,
Rate-Limiting, Backoff, Circuit Breaker, Bronze-Archivierung, Bus-Zustellung,
Metriken, Schema-Drift-Erkennung, Kill-Switch, sauberes Herunterfahren.

---

## Ein vollständiger Konnektor

Das ist alles, was eine neue Quelle braucht — 44 Zeilen, davon die Hälfte
Kommentar:

```python
from argus_connector import BaseConnector, CanonicalMessage, FetchResult, RawRecord


class UsgsEarthquakeConnector(BaseConnector):
    """Erdbeben des USGS, seit dem letzten bekannten Zeitpunkt."""

    # Aus diesen Feldern entsteht der dedupe_key. Sie müssen stabil sein:
    # dieselbe Meldung, zweimal geholt, muss denselben Schlüssel ergeben.
    dedupe_fields = ("id",)

    BASE = "https://earthquake.usgs.gov/fdsnws/event/1/query"

    async def fetch(self, cursor):
        # `cursor` ist das, was beim letzten erfolgreichen Batch festgeschrieben
        # wurde — hier ein ISO-Zeitstempel. Beim allerersten Lauf: None.
        params = {"format": "geojson", "orderby": "time-asc", "limit": 500}
        if cursor:
            params["starttime"] = cursor

        # get_json() erledigt Rate-Limiting, Retry mit Jitter, Circuit Breaker,
        # Retry-After und die Uhrendrift-Messung. Fehler kommen klassifiziert
        # zurück: ein 404 wird nicht wiederholt, ein 503 schon.
        data = await self.get_json(self.BASE, params=params)

        features = data["features"]
        newest = max((f["properties"]["time"] for f in features), default=None)
        return FetchResult(
            records=[
                RawRecord(payload=f, source_timestamp=f["properties"]["time"] / 1000)
                for f in features
            ],
            # Der neue Cursor wird erst festgeschrieben, wenn der Batch
            # zugestellt ist. Ein Absturz davor wiederholt ihn.
            next_cursor=self.to_iso(newest) if newest else cursor,
            has_more=len(features) >= 500,
        )

    def normalize(self, raw):
        props, coords = raw.payload["properties"], raw.payload["geometry"]["coordinates"]
        return [
            CanonicalMessage(
                subject_suffix="disaster.earthquake",
                payload={
                    "schema_version": self.settings.schema_version,
                    "type": "natural.earthquake",
                    "title": props["title"],
                    "occurred_at": {"start": self.to_iso(props["time"]), "precision": "second"},
                    "geo": {
                        "geometry": {"point": {"lon": coords[0], "lat": coords[1]}},
                        "precision": "exact",
                    },
                    "magnitude": {"scale": "richter", "value": props["mag"], "unit": "M"},
                    "dedupe_key": self.dedupe_key_for(raw.payload),
                },
                dedupe_key=self.dedupe_key_for(raw.payload),
                observed_at=props["time"] / 1000,
            )
        ]
```

Starten:

```python
import asyncio
from argus_connector import ConnectorRunner, ConnectorSettings, NatsPublisher, BronzeWriter
from argus_connector.bronze import S3ObjectStore
from argus_connector.runner import build_cursor_store


async def main():
    settings = ConnectorSettings()  # alles aus der Umgebung
    connector = UsgsEarthquakeConnector(settings)
    runner = ConnectorRunner(
        connector,
        settings=settings,
        cursor_store=build_cursor_store(settings),
        publisher=NatsPublisher(settings.nats.url, stream=settings.nats.stream),
        bronze=BronzeWriter(S3ObjectStore(settings.bronze.bucket), source_id=settings.source_id),
    )
    runner.install_signal_handlers()
    await runner.run()


asyncio.run(main())
```

---

## Die Reihenfolge im Batch

Der ganze Punkt des Frameworks steckt in sechs Schritten:

```
1. fetch          Daten holen
2. begin(cursor)  Absicht festhalten  ──┐
3. bronze         Rohdaten archivieren  │  Absturz hier drin
4. normalize      kanonisieren          │  ⇒ Batch wird wiederholt
5. publish        zustellen + Ack       │
6. commit         Cursor festschreiben ─┘
```

Ein Absturz zwischen 1 und 6 wiederholt den Batch. **Doppelte Nachrichten sind
erlaubt und über den `dedupe_key` erkennbar; verlorene sind es nicht.** Der
umgekehrte Fehler — ein fortgeschriebener Cursor für Daten, die nie ankamen —
ist der eine, den das System nicht machen darf.

Zwei Mechanismen fangen die Wiederholung auf:

- Jede Nachricht trägt ihren `dedupe_key` als `Nats-Msg-Id`. JetStream verwirft
  Wiederholungen innerhalb seines Dedupe-Fensters.
- Danach greift derselbe Schlüssel als Unique-Constraint in der Datenbank.

Verifiziert in `tests/test_crash_recovery.py`: ein echter Prozess, mit `SIGKILL`
getötet, neu gestartet — kein Datensatz fehlt, höchstens ein Batch kommt doppelt.

---

## Module

| Modul          | Aufgabe                                                          |
| -------------- | ---------------------------------------------------------------- |
| `base.py`      | Konnektor-Vertrag (Protocol) und Basisklasse mit HTTP-Client     |
| `config.py`    | Pydantic-Settings, alles aus `ARGUS_*`-Umgebungsvariablen        |
| `cursor.py`    | Zwei-Phasen-Cursor; Valkey + Postgres, verkettet                 |
| `ratelimit.py` | Token-Bucket, adaptive Drosselung bei 429, `Retry-After`         |
| `retry.py`     | Fehlerklassifikation, Backoff mit vollem Jitter, Circuit Breaker |
| `bronze.py`    | Gepufferte, gebündelte S3-Archivierung mit Spool-Fallback        |
| `bus.py`       | NATS-JetStream-Publisher, at-least-once mit Bestätigung          |
| `metrics.py`   | Prometheus                                                       |
| `drift.py`     | Schema-Drift-Erkennung                                           |
| `runner.py`    | Prozess-Lebenszyklus, Signale, Kill-Switch                       |

---

## Entscheidungen, die im Betrieb zählen

**Cursor: erst nach dem Publish festschreiben.** `begin()` schreibt einen
`pending`-Eintrag, `commit()` erst nach der bestätigten Zustellung. Beim
Neustart wird ab dem _festgeschriebenen_ Stand wieder aufgesetzt, nie ab
`pending` — der ist reine Diagnose und sagt, welcher Batch unterbrochen wurde.

**Valkey und Postgres verkettet.** Gelesen wird bevorzugt aus dem Cache,
geschrieben **zuerst** dauerhaft. Ein geleerter Cache darf nie bedeuten, dass
ein Konnektor von vorn anfängt; ein Absturz zwischen beiden Schreibvorgängen
darf keinen Cursor hinterlassen, der nur flüchtig existiert.

**Fehler werden klassifiziert, nicht gezählt.** DNS, TLS und „Verbindung
abgelehnt" sind drei verschiedene Befunde — „Netz prüfen", „Zertifikat prüfen",
„Dienst prüfen". Ein 404 wird nicht wiederholt und lässt den Circuit Breaker in
Ruhe; ein 503 tut beides.

**Voller Jitter statt „exponentiell plus etwas Rauschen".** Bei einem Ausfall,
der viele Konnektoren gleichzeitig trifft, verteilt nur der volle Jitter die
Wiederkehr wirklich — sonst kommen alle im selben Moment zurück und legen die
gerade erholte Quelle erneut um.

**Drosselung: multiplikativ nachgeben, additiv erholen.** Dasselbe Muster wie
bei der Überlastregelung in TCP und aus demselben Grund. Wer nach einem 429
sofort wieder auf volle Rate geht, bekommt den nächsten 429. `Retry-After` hat
Vorrang vor jedem berechneten Backoff — die Quelle weiß besser, wann sie kann.

**Bronze wird gebündelt, nie verloren.** Ein PUT je Nachricht wären bei AIS
Millionen winziger Objekte pro Tag. Geschrieben wird bei Stundenwechsel,
Größen- oder Altersgrenze und beim Herunterfahren. Ist der Objektspeicher weg,
wandert das Bündel in einen lokalen Spool und wird später nachgereicht —
alles andere im System ist aus Bronze wiederherstellbar, Bronze selbst nicht.

**Schema-Drift meldet, verwirft nicht.** Der Detektor lernt die Form aus den
ersten Datensätzen und meldet danach neue Felder, verschwundene Felder,
Typ- und Kardinalitätswechsel — jede Abweichung genau einmal, sonst erzeugt eine
geänderte Quelle eine Meldung je Datensatz. `null` und `int`/`float` gelten
nicht als Wechsel.

**Metriken existieren ab dem Start.** Alle Zeitreihen werden mit ihren Labels
vorbelegt. Eine Metrik, die erst mit dem ersten Fehler erscheint, lässt sich
weder in einem Dashboard noch in einer Alarmregel sauber benutzen: „keine
Zeitreihe" und „keine Fehler" sähen gleich aus.

---

## Metriken

Pflicht laut Aufgabenstellung, alle mit den Labels `connector` und `source`:

| Metrik                             | Typ     | Bedeutung                                                             |
| ---------------------------------- | ------- | --------------------------------------------------------------------- |
| `connector_messages_total`         | Counter | nach Stufe: `fetched`, `normalized`, `published`, `skipped_duplicate` |
| `connector_errors_total`           | Counter | nach Fehlerklasse (`dns`, `tls`, `rate_limited`, …)                   |
| `connector_lag_seconds`            | Gauge   | jetzt minus `observed_at` der letzten Nachricht                       |
| `connector_last_success_timestamp` | Gauge   | Unix-Zeit des letzten erfolgreichen Durchlaufs                        |

Dazu im Betrieb: `connector_fetch_duration_seconds`,
`connector_publish_duration_seconds`, `connector_rate_limit_delay_seconds_total`,
`connector_rate_limit_requests_per_second`, `connector_circuit_state`,
`connector_clock_skew_seconds`, `connector_cursor_commits_total`,
`connector_bronze_flushes_total`, `connector_bronze_buffered_records`,
`connector_schema_drift_total`, `connector_up`.

---

## Kill-Switch

Zur Laufzeit über NATS, ohne Neustart:

```sh
nats pub 'argus.control.connector.ingest-sea' \
  '{"command":"pause","connector_id":"ingest-sea","reason":"Quelle in Wartung"}'
nats pub 'argus.control.connector.all' '{"command":"resume","connector_id":"*"}'
```

Befehle: `pause`, `resume`, `stop`. Ohne `connector_id` oder mit `"*"` gilt der
Befehl für alle. Ein angehaltener Konnektor fasst die Quelle nicht mehr an —
er wartet, ohne Abrufe zu erzeugen.

---

## Konfiguration

Alles über `ARGUS_<BEREICH>__<FELD>`:

```sh
ARGUS_CONNECTOR_ID=ingest-sea
ARGUS_SOURCE_ID=aisstream
ARGUS_NATS__URL=nats://nats:4222
ARGUS_CURSOR__BACKEND=chained
ARGUS_CURSOR__VALKEY_URL=redis://valkey:6379/0
ARGUS_CURSOR__POSTGRES_DSN=postgresql://argus:...@postgres:5432/argus
ARGUS_BRONZE__BUCKET=argus-bronze
ARGUS_RATELIMIT__REQUESTS_PER_SECOND=5
ARGUS_RETRY__MAX_ATTEMPTS=5
```

Vollständige Liste mit Kommentaren in `argus_connector/config.py`.

---

## Tests

```sh
export ARGUS_TEST_POSTGRES_DSN='postgresql://argus:argus@localhost:5432/argus'
.venv/bin/python -m pytest --cov=argus_connector
```

216 Tests, 91 % Abdeckung. Postgres und Valkey werden als **echte** Dienste
benutzt, wenn erreichbar, und die betreffenden Tests sonst übersprungen — nicht
als bestanden gemeldet. Ob ein Cursor einen Prozessabsturz überlebt, zeigt kein
Mock.

Die beiden Abnahmekriterien liegen in eigenen Dateien:

- `tests/test_crash_recovery.py` — Prozess mit `SIGKILL` getötet, neu gestartet,
  Vergleich der zugestellten Menge. Auch: dreimal hintereinander töten, und
  `SIGTERM` führt den laufenden Batch zu Ende.
- `tests/test_throttling.py` — echter HTTP-Server, der 429 liefert. Geprüft wird
  die Ratenhalbierung, die _an der Uhr ablesbare_ Verlangsamung, die Einhaltung
  von `Retry-After` und die Erholung.

---

## Bekannte Grenzen

- **Nur Poll-Betrieb ist erprobt.** `ConnectorMode.STREAM` (WebSocket, TCP) ist
  im Vertrag vorgesehen, aber der Runner ist auf Batches ausgelegt. Ein
  Stream-Konnektor braucht eine eigene Schleife, die dieselben sechs Schritte in
  Zeitfenstern statt in Seiten ausführt.
- **Ein Prozess, eine Quelle.** Mehrere Quellen je Prozess sind über mehrere
  Runner möglich, aber der Kill-Switch und die Metriken sind auf eine
  `connector_id` ausgelegt.
- **Kein verteiltes Sperren.** Zwei Prozesse mit derselben `connector_id`
  überschreiben einander den Cursor. Das gehört in die Orchestrierung
  (eine Replik je Konnektor), nicht ins SDK.
- **Bronze-Spool wächst unbegrenzt**, solange der Objektspeicher weg ist. Eine
  Obergrenze mit definiertem Verhalten bei Erreichen fehlt noch — bis dahin
  gehört der freie Platz des Spool-Verzeichnisses überwacht.
- **`botocore` ist synchron.** Die S3-Aufrufe laufen in einem Thread. Das
  blockiert die Ereignisschleife nicht, ist aber kein echtes async I/O — bei
  einem Aufruf je Stunde und Quelle lohnt die zusätzliche Abhängigkeit nicht.
