"""Prometheus-Metriken je Konnektor.

Die vier Pflichtmetriken aus der Aufgabenstellung heissen genau so, wie sie
heissen muessen; der Rest ist das, was man im Betrieb tatsaechlich braucht,
wenn nachts eine Quelle stehenbleibt.

Alle Metriken tragen die Labels connector und source. Ein eigener
CollectorRegistry je Instanz macht die Tests unabhaengig voneinander -
Prometheus-Metriken sind sonst globaler Zustand.
"""

from __future__ import annotations

import time

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, start_http_server

from argus_connector.retry import ErrorKind

# Aufteilung nach dem, was man unterscheiden will: Sekundenbruchteile bei
# gesunden Quellen, Minuten bei kranken.
_DURATION_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300)


class ConnectorMetrics:
    """Metriken eines Konnektorprozesses."""

    def __init__(
        self,
        connector_id: str,
        source_id: str,
        registry: CollectorRegistry | None = None,
    ) -> None:
        self.connector_id = connector_id
        self.source_id = source_id
        self.registry = registry if registry is not None else CollectorRegistry()
        labels = ("connector", "source")
        self._labels = {"connector": connector_id, "source": source_id}

        # --- Pflichtmetriken ------------------------------------------
        self.messages_total = Counter(
            "connector_messages_total",
            "Verarbeitete Nachrichten, nach Verarbeitungsstufe.",
            (*labels, "stage"),
            registry=self.registry,
        )
        self.errors_total = Counter(
            "connector_errors_total",
            "Fehler, nach Fehlerklasse.",
            (*labels, "kind"),
            registry=self.registry,
        )
        self.lag_seconds = Gauge(
            "connector_lag_seconds",
            "Alter der zuletzt verarbeiteten Beobachtung: jetzt minus observed_at. "
            "Die eigentliche Kennzahl fuer 'haengt die Quelle hinterher'.",
            labels,
            registry=self.registry,
        )
        self.last_success_timestamp = Gauge(
            "connector_last_success_timestamp",
            "Unix-Zeit des letzten erfolgreichen Durchlaufs.",
            labels,
            registry=self.registry,
        )

        # --- Betriebsmetriken -----------------------------------------
        self.fetch_duration = Histogram(
            "connector_fetch_duration_seconds",
            "Dauer eines Abrufs bei der Quelle.",
            labels,
            buckets=_DURATION_BUCKETS,
            registry=self.registry,
        )
        self.publish_duration = Histogram(
            "connector_publish_duration_seconds",
            "Dauer der Veroeffentlichung eines Batches auf dem Bus.",
            labels,
            buckets=_DURATION_BUCKETS,
            registry=self.registry,
        )
        self.rate_limit_delay = Counter(
            "connector_rate_limit_delay_seconds_total",
            "Aufsummierte Wartezeit durch den Rate-Limiter. Steigt der Wert, "
            "ist die Quelle der Engpass, nicht der Konnektor.",
            labels,
            registry=self.registry,
        )
        self.rate_limit_current = Gauge(
            "connector_rate_limit_requests_per_second",
            "Aktuell erlaubte Abrufrate. Faellt bei HTTP 429, erholt sich danach.",
            labels,
            registry=self.registry,
        )
        self.circuit_state = Gauge(
            "connector_circuit_state",
            "Zustand des Circuit Breakers: 0 geschlossen, 1 halb offen, 2 offen.",
            labels,
            registry=self.registry,
        )
        self.clock_skew_seconds = Gauge(
            "connector_clock_skew_seconds",
            "Gemessener Versatz zwischen Quellenuhr und Systemuhr. Positiv: "
            "die Quelle geht vor.",
            labels,
            registry=self.registry,
        )
        self.cursor_commits_total = Counter(
            "connector_cursor_commits_total",
            "Festgeschriebene Cursor. Ein stagnierender Wert bei laufendem "
            "Prozess bedeutet: es kommt nichts durch.",
            labels,
            registry=self.registry,
        )
        self.bronze_flushes_total = Counter(
            "connector_bronze_flushes_total",
            "Geschriebene Bronze-Buendel, nach Ergebnis.",
            (*labels, "result"),
            registry=self.registry,
        )
        self.bronze_buffered_records = Gauge(
            "connector_bronze_buffered_records",
            "Noch nicht geschriebene Rohsaetze im Puffer.",
            labels,
            registry=self.registry,
        )
        self.drift_events_total = Counter(
            "connector_schema_drift_total",
            "Erkannte Schemaabweichungen, nach Art.",
            (*labels, "kind"),
            registry=self.registry,
        )
        self.up = Gauge(
            "connector_up",
            "1 wenn der Konnektor laeuft und nicht ueber den Kill-Switch "
            "angehalten wurde.",
            labels,
            registry=self.registry,
        )

        # Labels vorbelegen, damit die Zeitreihen ab dem Start existieren und
        # nicht erst beim ersten Ereignis auftauchen. Eine Metrik, die erst mit
        # dem ersten Fehler erscheint, laesst sich weder in einem Dashboard
        # noch in einer Alarmregel sauber benutzen: "keine Zeitreihe" und
        # "keine Fehler" sehen dann gleich aus.
        for stage in ("fetched", "normalized", "published", "skipped_duplicate"):
            self.messages_total.labels(**self._labels, stage=stage)
        for kind in ErrorKind:
            self.errors_total.labels(**self._labels, kind=kind.value)
        for counter in (
            self.rate_limit_delay,
            self.cursor_commits_total,
        ):
            counter.labels(**self._labels)
        for gauge in (
            self.lag_seconds,
            self.last_success_timestamp,
            self.bronze_buffered_records,
            self.clock_skew_seconds,
        ):
            gauge.labels(**self._labels)
        self.up.labels(**self._labels).set(0)
        self.circuit_state.labels(**self._labels).set(0)

    # -- bequeme Zugriffe ------------------------------------------------

    def count(self, stage: str, amount: int = 1) -> None:
        self.messages_total.labels(**self._labels, stage=stage).inc(amount)

    def error(self, kind: str, amount: int = 1) -> None:
        self.errors_total.labels(**self._labels, kind=kind).inc(amount)

    def drift(self, kind: str) -> None:
        self.drift_events_total.labels(**self._labels, kind=kind).inc()

    def bronze_flush(self, result: str) -> None:
        self.bronze_flushes_total.labels(**self._labels, result=result).inc()

    def observe_lag(self, observed_at_epoch: float) -> None:
        self.lag_seconds.labels(**self._labels).set(max(0.0, time.time() - observed_at_epoch))

    def mark_success(self) -> None:
        self.last_success_timestamp.labels(**self._labels).set(time.time())

    def set_up(self, value: bool) -> None:
        self.up.labels(**self._labels).set(1 if value else 0)

    def set_circuit_state(self, state: str) -> None:
        self.circuit_state.labels(**self._labels).set(
            {"closed": 0, "half_open": 1, "open": 2}.get(state, 0)
        )

    def set_rate(self, rps: float) -> None:
        self.rate_limit_current.labels(**self._labels).set(rps)

    def add_rate_limit_delay(self, seconds: float) -> None:
        if seconds > 0:
            self.rate_limit_delay.labels(**self._labels).inc(seconds)

    def set_clock_skew(self, seconds: float) -> None:
        self.clock_skew_seconds.labels(**self._labels).set(seconds)

    def cursor_committed(self) -> None:
        self.cursor_commits_total.labels(**self._labels).inc()

    def set_bronze_buffer(self, count: int) -> None:
        self.bronze_buffered_records.labels(**self._labels).set(count)

    def fetch_timer(self):
        return self.fetch_duration.labels(**self._labels).time()

    def publish_timer(self):
        return self.publish_duration.labels(**self._labels).time()

    def serve(self, host: str, port: int) -> None:
        start_http_server(port, addr=host, registry=self.registry)
