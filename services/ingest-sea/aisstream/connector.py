"""Der AIS-Konnektor.

Verbindet den WebSocket-Leser (stream.py) mit dem Vertrag des SDK
(BaseConnector) und damit mit Cursor, Bronze, Bus, Metriken und
Kill-Switch aus Prompt 4.

WIE EIN STROM IN EINEN POLL-RAHMEN PASST
----------------------------------------
Der Runner des SDK ruft `fetch(cursor)` in einer Schleife auf und erwartet
einen Stapel. Ein WebSocket liefert aber, wann er will. Die Bruecke ist die
Warteschlange: der Leser laeuft dauerhaft und fuellt sie, `fetch()` entnimmt
einen Stapel.

Der Gewinn ist nicht Bequemlichkeit, sondern die Stapelsemantik des Runners -
Bronze vor Publish, Cursor erst nach der Bestaetigung. Ein Stromkonnektor, der
Nachricht fuer Nachricht durchreicht, hat diese Reihenfolge nicht und verliert
bei jedem Absturz genau das, was gerade unterwegs war.

WAS DER CURSOR HIER BEDEUTET
----------------------------
Nichts, was einen Wiederanlauf ermoeglicht: AISStream hat kein Replay. Ein
Neustart beginnt beim naechsten gesendeten Satz, und was waehrend der Auszeit
gefahren wurde, ist weg. Der Cursor haelt deshalb nur fest, wie weit man
gekommen war - fuer die Luckenanzeige (Prinzip 4), nicht fuer die
Wiederaufnahme. Wer hier eine Wiederaufnahme hineinliest, plant einen
Wiederanlauf, den es nicht gibt.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from aisstream.config import AisStreamSettings
from aisstream.metrics import AisMetrics
from aisstream.normalize import Normalizer, subject_suffix_for
from aisstream.parser import (
    MalformedMessageError,
    ParsedMessage,
    UnsupportedMessageTypeError,
    parse,
)
from aisstream.stream import AisStreamClient, FatalStreamError
from argus_connector import (
    BaseConnector,
    CanonicalMessage,
    ConnectorMetrics,
    ConnectorMode,
    ConnectorSettings,
    FetchResult,
    HealthStatus,
    RawRecord,
)

logger = logging.getLogger(__name__)


class AisStreamConnector(BaseConnector):
    """Maritimer Echtzeit-Konnektor gegen AISStream.io."""

    id = "ingest-sea-aisstream"
    mode = ConnectorMode.STREAM
    # Der dedupe_key wird in normalize.py aus den Fachfeldern gebildet, nicht
    # ueber DedupeKeyBuilder: er muss fuer Position und Stammdaten
    # unterschiedlich zusammengesetzt sein, und beide entstehen aus derselben
    # Rohnachricht. Ein Schluessel pro Rohsatz reicht dafuer nicht.
    dedupe_fields = ()

    def __init__(
        self,
        settings: ConnectorSettings,
        ais_settings: AisStreamSettings,
        *,
        metrics: ConnectorMetrics | None = None,
        client: AisStreamClient | None = None,
        clock: Any = time.time,
    ) -> None:
        super().__init__(settings, metrics=metrics)
        self.ais_settings = ais_settings
        self.clock = clock
        self.ais_metrics = AisMetrics(self.metrics)

        self.stream = client or AisStreamClient(ais_settings)
        # Nach der Zuweisung, nicht im Konstruktor: ein eingespeister Client
        # soll dieselben Metriken fuellen wie ein selbst gebauter.
        self.stream.on_reconnect = self._on_reconnect
        self.stream.on_drop = self.ais_metrics.drop
        self.normalizer = Normalizer(
            collector=f"{settings.connector_id}@{settings.connector_version}",
            schema_version=settings.schema_version,
            max_implied_speed_kn=ais_settings.max_implied_speed_kn,
            max_future_skew_s=settings.max_clock_skew_s,
            position_history_size=ais_settings.position_history_size,
        )

        # Suffixe einmal beim Start ausrechnen. Passt das Praefix nicht zu den
        # zugesagten Subjects, faellt der Prozess hier um - und nicht erst,
        # wenn nach zwei Tagen jemand fragt, warum der Stream leer ist.
        prefix = settings.nats.subject_prefix
        self._position_suffix = subject_suffix_for("position", prefix=prefix)
        self._static_suffix = subject_suffix_for("static", prefix=prefix)

        self._unsupported_seen: set[str] = set()
        self._messages_seen = 0
        self._observations = 0
        self._entities = 0
        self._last_disconnect_at: float | None = None

    # -- Verbindungsereignisse -------------------------------------------

    def _on_reconnect(self, attempt: int, delay: float) -> None:
        self.ais_metrics.reconnect()
        if self._last_disconnect_at is None:
            self._last_disconnect_at = time.monotonic()

    def _note_connection_state(self) -> None:
        connected = self.stream.connected
        self.ais_metrics.set_connected(connected)
        self.ais_metrics.set_queue_depth(self.stream.pending)
        if connected and self._last_disconnect_at is not None:
            self.ais_metrics.reconnect_took(time.monotonic() - self._last_disconnect_at)
            self._last_disconnect_at = None

    # -- Vertrag ----------------------------------------------------------

    async def health(self) -> HealthStatus:
        if self.stream.fatal is not None:
            return HealthStatus.failing(f"dauerhaft abgewiesen: {self.stream.fatal}")
        if not self.stream.running:
            return HealthStatus.failing("Leser laeuft nicht")
        if not self.stream.connected:
            return HealthStatus.failing("keine Verbindung zu AISStream")
        if self.stream.last_message_at is None:
            return HealthStatus.ok("verbunden, noch keine Nachricht")
        silence = time.monotonic() - self.stream.last_message_at
        if silence > self.ais_settings.idle_timeout_s:
            return HealthStatus.failing(f"seit {silence:.0f} s keine Nachricht")
        return HealthStatus.ok(
            f"{self.stream.messages_received} Nachrichten, {self.stream.pending} in der Schlange",
            latency_s=silence,
        )

    async def fetch(self, cursor: Any | None) -> FetchResult:
        """Entnimmt einen Stapel aus der Warteschlange.

        Startet den Leser beim ersten Aufruf. Ein leerer Stapel ist kein
        Fehler - er bedeutet, dass in `max_batch_wait_s` nichts kam.
        """
        if self.stream.fatal is not None:
            raise self.stream.fatal
        if not self.stream.running:
            self.stream.start()

        raw_messages = await self.stream.batch(
            max_size=self.ais_settings.max_batch_size,
            max_wait_s=self.ais_settings.max_batch_wait_s,
        )
        self._note_connection_state()

        if not raw_messages:
            return FetchResult(records=[], next_cursor=cursor, has_more=False)

        now = self.clock()
        records = [
            RawRecord(
                payload=message,
                fetched_at=now,
                # Der Quellzeitstempel wird hier noch nicht geparst: das
                # passiert in normalize(), und zweimal zu parsen kostet bei
                # 2.000 Nachrichten/s messbar Zeit.
                cursor_hint=None,
            )
            for message in raw_messages
        ]
        self._messages_seen += len(records)

        next_cursor = {
            "messages_seen": self._messages_seen,
            "observations": self._observations,
            "entities": self._entities,
            "connections": self.stream.successful_connections,
            "dropped": self.stream.messages_dropped,
            "at": now,
        }
        return FetchResult(
            records=records,
            next_cursor=next_cursor,
            # Ist die Schlange noch voll, sofort weitermachen statt das
            # Poll-Intervall abzuwarten. Sonst kommt der Konnektor bei einem
            # Rueckstau nie wieder heraus.
            has_more=self.stream.pending >= self.ais_settings.max_batch_size,
        )

    def normalize(self, raw: RawRecord) -> list[CanonicalMessage]:
        """Eine Rohnachricht -> null bis zwei kanonische Nachrichten.

        Zwei bei Typ 19: der einzige AIS-Satz, der Position und Stammdaten in
        einer Nachricht traegt. Null bei einem Typ, den wir nicht uebersetzen.
        """
        payload = raw.payload
        if not isinstance(payload, dict):
            raise MalformedMessageError("Rohsatz ist kein Objekt")

        try:
            parsed = parse(payload)
        except UnsupportedMessageTypeError as exc:
            self.ais_metrics.unsupported(exc.message_type)
            if exc.message_type not in self._unsupported_seen:
                # Einmal je Typ, nicht einmal je Nachricht. Bei 2.000
                # Nachrichten/s wuerde ein unbekannter Typ sonst das
                # Protokoll fluten und die eigentlichen Fehler verdecken.
                self._unsupported_seen.add(exc.message_type)
                logger.info(
                    "Nachrichtentyp %r wird nicht uebersetzt und ab jetzt nur "
                    "noch gezaehlt (Metrik aisstream_unsupported_messages_total).",
                    exc.message_type,
                )
            return []

        self.ais_metrics.message(parsed.message_type)
        now = self.clock()
        clock_skew_ms = self._clock_skew_ms(parsed, now)
        messages: list[CanonicalMessage] = []

        position = self.normalizer.to_observation(
            parsed, now=now, raw_ref=raw.raw_ref, clock_skew_ms=clock_skew_ms
        )
        if position is not None:
            observation, dedupe_key, observed_at = position
            self._observations += 1
            self._record_flags(observation.get("quality", {}).get("flags", []))
            self._record_lag(observed_at, now)
            messages.append(
                CanonicalMessage(
                    subject_suffix=self._position_suffix,
                    payload=observation,
                    dedupe_key=dedupe_key,
                    observed_at=observed_at,
                )
            )

        static = self.normalizer.to_entity(
            parsed, now=now, raw_ref=raw.raw_ref, clock_skew_ms=clock_skew_ms
        )
        if static is not None:
            entity, dedupe_key, observed_at = static
            self._entities += 1
            self._record_flags(entity.get("attributes", {}).get("quality_flags", []))
            messages.append(
                CanonicalMessage(
                    subject_suffix=self._static_suffix,
                    payload=entity,
                    dedupe_key=dedupe_key,
                    observed_at=observed_at,
                )
            )
        return messages

    # -- Hilfen -----------------------------------------------------------

    def _clock_skew_ms(self, parsed: ParsedMessage, now: float) -> int | None:
        """Versatz zwischen Quellzeit und Systemuhr, in Millisekunden.

        Nur bei Zeitstempeln aus der Zukunft gefuellt. Ein normaler Lag ist
        keine Uhrendrift, sondern Laufzeit - und beides zu vermengen macht die
        Kennzahl unbrauchbar.
        """
        if parsed.received_at is None:
            return None
        skew = parsed.received_at - now
        if skew <= 0:
            return None
        return int(skew * 1000)

    def _record_flags(self, flags: Any) -> None:
        if isinstance(flags, list):
            for flag in flags:
                self.ais_metrics.flag(str(flag))

    def _record_lag(self, observed_at: float | None, now: float) -> None:
        if observed_at is not None:
            self.ais_metrics.observe_lag(now - observed_at)

    async def close(self) -> None:
        await self.stream.stop()
        self.ais_metrics.set_connected(False)
        await super().close()


__all__ = ["AisStreamConnector", "FatalStreamError"]
