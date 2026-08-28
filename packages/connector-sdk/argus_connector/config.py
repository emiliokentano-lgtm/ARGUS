"""Konfiguration ueber Umgebungsvariablen.

Kein Wert steht im Code (Definition of Done, Punkt 5). Alles kommt aus der
Umgebung, mit sprechenden Namen und Standardwerten, die fuer die Entwicklung
funktionieren und in Produktion bewusst ueberschrieben werden.

Namensschema: ARGUS_<BEREICH>__<FELD>, z. B.

    ARGUS_CONNECTOR_ID=ingest-sea
    ARGUS_NATS__URL=nats://nats:4222
    ARGUS_RATELIMIT__REQUESTS_PER_SECOND=5
    ARGUS_BRONZE__BUCKET=argus-bronze
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class NatsSettings(BaseModel):
    """Message Bus."""

    url: str = "nats://localhost:4222"
    # Stream, in den veroeffentlicht wird. Muss existieren; das Anlegen ist
    # Sache des Stacks (infra/compose/init/nats), nicht des Konnektors.
    stream: str = "ARGUS_RAW"
    subject_prefix: str = "argus.raw"
    # Kontroll-Subject fuer den Kill-Switch. Wildcard, damit ein Befehl an
    # alle Konnektoren moeglich ist.
    control_subject: str = "argus.control.connector"
    connect_timeout_s: float = 5.0
    # Wartezeit auf die JetStream-Bestaetigung. Ohne Bestaetigung gilt eine
    # Nachricht als nicht zugestellt und der Cursor wird nicht festgeschrieben.
    ack_timeout_s: float = 10.0
    max_reconnect_attempts: int = -1  # unbegrenzt
    # Zeitfenster, in dem JetStream Nachrichten mit gleicher Nats-Msg-Id
    # verwirft. Muss zum dupe_window des Streams passen.
    dedupe_window_s: float = 120.0


class BronzeSettings(BaseModel):
    """Rohdatenarchiv (Kapitel 5.2: jede Rohantwort unveraendert)."""

    endpoint_url: str | None = None  # None = AWS-Standard
    bucket: str = "argus-bronze"
    region: str = "us-east-1"
    access_key: str | None = None
    secret_key: str | None = None

    # Ziel ist eine Datei je Quelle und Stunde, nicht eine je Nachricht.
    # Geschrieben wird, sobald eine dieser Grenzen erreicht ist.
    max_batch_records: int = 50_000
    max_batch_bytes: int = 64 * 1024 * 1024
    max_batch_age_s: float = 3600.0
    compress: bool = True

    # Wenn der Objektspeicher nicht erreichbar ist, wandern die Buendel
    # hierhin und werden spaeter nachgereicht. Bronze darf nie verloren gehen.
    spool_dir: str = "/var/lib/argus/bronze-spool"
    spool_retry_interval_s: float = 60.0


class CursorSettings(BaseModel):
    """Wiederaufnahmepunkt."""

    # valkey ist schnell, postgres ist dauerhaft. 'chained' benutzt beides:
    # lesen bevorzugt aus Valkey, schreiben in beide, und wenn Valkey leer ist
    # (Neustart, Verdraengung), kommt der Wert aus Postgres.
    backend: Literal["chained", "valkey", "postgres", "memory"] = "chained"
    valkey_url: str = "redis://localhost:6379/0"
    postgres_dsn: str | None = None
    key_prefix: str = "argus:cursor"
    # Schema fuer die Postgres-Ablage. Bewusst getrennt vom Domaenenschema.
    postgres_schema: str = "argus_connector"


class RateLimitSettings(BaseModel):
    """Token-Bucket je Quelle."""

    requests_per_second: float = 5.0
    burst: int = 10
    # Hoeflichkeitsverzoegerung zwischen zwei Abrufen derselben Domain.
    politeness_delay_s: float = 0.0

    # Verhalten bei HTTP 429. Multiplikative Verringerung, additive Erholung -
    # dasselbe Muster wie bei der Ueberlastregelung in TCP, aus demselben Grund:
    # schnell nachgeben, langsam wieder zugreifen.
    backoff_factor: float = 0.5
    recovery_step: float = 0.1
    recovery_interval_s: float = 30.0
    min_requests_per_second: float = 0.1

    @field_validator("backoff_factor")
    @classmethod
    def _factor_below_one(cls, v: float) -> float:
        if not 0 < v < 1:
            raise ValueError("backoff_factor muss zwischen 0 und 1 liegen")
        return v


class RetrySettings(BaseModel):
    """Wiederholung und Circuit Breaker."""

    max_attempts: int = 5
    base_delay_s: float = 0.5
    max_delay_s: float = 60.0
    # Full Jitter: delay = random(0, min(max, base * 2^n)). Verhindert, dass
    # alle Konnektoren nach einem Ausfall im Gleichtakt wiederkommen.
    jitter: bool = True

    circuit_failure_threshold: int = 5
    circuit_reset_timeout_s: float = 60.0
    # Erfolge im Halb-offen-Zustand, bevor der Kreis wieder schliesst.
    circuit_success_threshold: int = 2


class MetricsSettings(BaseModel):
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 9100


class ConnectorSettings(BaseSettings):
    """Gesamtkonfiguration eines Konnektorprozesses."""

    model_config = SettingsConfigDict(
        env_prefix="ARGUS_",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    # Wer bin ich. connector_id identifiziert den Prozess, source_id die Quelle
    # im Quellenregister - ein Konnektor kann mehrere Quellen bedienen.
    connector_id: str = "unnamed-connector"
    source_id: str = "unknown"
    connector_version: str = "0.0.0"
    schema_version: str = "1.0.0"

    # Wartezeit zwischen zwei Durchlaeufen im Poll-Betrieb.
    poll_interval_s: float = 60.0
    # Groesse eines Batches, nach dem Cursor und Bronze festgeschrieben werden.
    # Kleiner = weniger Doppelzustellung nach einem Absturz, mehr Overhead.
    batch_size: int = 500
    # Obergrenze fuer die Dauer eines Durchlaufs.
    fetch_timeout_s: float = 120.0

    # Kill-Switch (Kapitel 5.2): zur Laufzeit ueber NATS umschaltbar.
    enabled: bool = True

    # Zulaessige Uhrendrift zwischen Quelle und System. Darueber wird die
    # Beobachtung als zeitlich unplausibel markiert.
    max_clock_skew_s: float = 300.0

    nats: NatsSettings = Field(default_factory=NatsSettings)
    bronze: BronzeSettings = Field(default_factory=BronzeSettings)
    cursor: CursorSettings = Field(default_factory=CursorSettings)
    ratelimit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    retry: RetrySettings = Field(default_factory=RetrySettings)
    metrics: MetricsSettings = Field(default_factory=MetricsSettings)
