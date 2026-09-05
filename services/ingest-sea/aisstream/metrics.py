"""Metriken, die nur der AIS-Konnektor hat.

Sie liegen in derselben Registry wie die SDK-Metriken, damit ein einziger
Scrape alles einsammelt.

ZUR PFLICHTMETRIK DER AUFGABENSTELLUNG
--------------------------------------
`ingest_lag_seconds` ist der Abstand zwischen `observed_at` und
`ingested_at` - also zwischen "das Schiff war dort" und "ARGUS weiss davon".
Das Akzeptanzkriterium nennt ein p95, und ein p95 braucht ein Histogramm; die
Gauge `connector_lag_seconds` aus dem SDK kann es nicht liefern, weil sie nur
den letzten Wert haelt. Beide existieren nebeneinander und messen dasselbe
mit unterschiedlicher Aufloesung: die Gauge fuer das Dashboard, das Histogramm
fuer die Zusage.

Die Bucketgrenzen sind um die 10-Sekunden-Zusage herum gelegt. Ein Histogramm,
dessen Grenzen nicht dort liegen, wo die Frage gestellt wird, beantwortet sie
nicht: mit Grenzen bei 5 und 30 waere "p95 unter 10 s" nicht entscheidbar.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

from argus_connector import ConnectorMetrics

_LAG_BUCKETS = (0.25, 0.5, 1, 2, 3, 5, 7.5, 10, 15, 30, 60, 120, 300)


class AisMetrics:
    """Ergaenzende Metriken. Teilt sich die Registry mit ConnectorMetrics."""

    def __init__(self, base: ConnectorMetrics) -> None:
        self.base = base
        labels = ("connector", "source")
        self._labels = {"connector": base.connector_id, "source": base.source_id}
        registry = base.registry

        self.ingest_lag = Histogram(
            "ingest_lag_seconds",
            "Abstand zwischen observed_at und ingested_at je Nachricht.",
            labels,
            buckets=_LAG_BUCKETS,
            registry=registry,
        )
        self.messages_by_type = Counter(
            "aisstream_messages_total",
            "Empfangene AISStream-Nachrichten, nach Nachrichtentyp.",
            (*labels, "message_type"),
            registry=registry,
        )
        self.unsupported_types = Counter(
            "aisstream_unsupported_messages_total",
            "Nachrichten eines Typs, den dieser Konnektor nicht uebersetzt.",
            (*labels, "message_type"),
            registry=registry,
        )
        self.quality_flags = Counter(
            "aisstream_quality_flags_total",
            "Vergebene Qualitaetsmarken, nach Art. Steigt 'invalid_position' "
            "oder 'impossible_speed', stimmt etwas mit der Quelle nicht.",
            (*labels, "flag"),
            registry=registry,
        )
        self.dropped = Counter(
            "aisstream_dropped_messages_total",
            "Wegen Rueckstaus verworfene Nachrichten. Jeder Zaehlerschritt ist "
            "verlorene Beobachtung - die Quelle kennt kein Replay.",
            labels,
            registry=registry,
        )
        self.reconnects = Counter(
            "aisstream_reconnects_total",
            "Wiederverbindungsversuche.",
            labels,
            registry=registry,
        )
        self.reconnect_seconds = Histogram(
            "aisstream_reconnect_duration_seconds",
            "Zeit vom Verbindungsverlust bis zur wiederhergestellten Verbindung.",
            labels,
            buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120),
            registry=registry,
        )
        self.connected = Gauge(
            "aisstream_connected",
            "1 wenn die WebSocket-Verbindung steht.",
            labels,
            registry=registry,
        )
        self.queue_depth = Gauge(
            "aisstream_queue_depth",
            "Nachrichten in der Warteschlange zwischen Leser und Verarbeitung.",
            labels,
            registry=registry,
        )

        # Vorbelegen, damit "keine Zeitreihe" und "kein Ereignis" nicht gleich
        # aussehen - dieselbe Begruendung wie im SDK.
        for counter in (self.dropped, self.reconnects):
            counter.labels(**self._labels)
        for gauge in (self.connected, self.queue_depth):
            gauge.labels(**self._labels).set(0)

    def observe_lag(self, seconds: float) -> None:
        # Negativer Lag bedeutet: die Quellzeit liegt in der Zukunft. Er wird
        # nicht in das Histogramm gerechnet - dort wuerde er als 0 erscheinen
        # und die Verteilung schoenen. Der Fall hat seine eigene Marke
        # ('future_timestamp') und gehoert dorthin.
        if seconds >= 0:
            self.ingest_lag.labels(**self._labels).observe(seconds)

    def message(self, message_type: str) -> None:
        self.messages_by_type.labels(**self._labels, message_type=message_type).inc()

    def unsupported(self, message_type: str) -> None:
        self.unsupported_types.labels(**self._labels, message_type=message_type).inc()

    def flag(self, name: str) -> None:
        self.quality_flags.labels(**self._labels, flag=name).inc()

    def drop(self, count: int = 1) -> None:
        self.dropped.labels(**self._labels).inc(count)

    def reconnect(self) -> None:
        self.reconnects.labels(**self._labels).inc()

    def reconnect_took(self, seconds: float) -> None:
        self.reconnect_seconds.labels(**self._labels).observe(seconds)

    def set_connected(self, value: bool) -> None:
        self.connected.labels(**self._labels).set(1 if value else 0)

    def set_queue_depth(self, value: int) -> None:
        self.queue_depth.labels(**self._labels).set(value)
