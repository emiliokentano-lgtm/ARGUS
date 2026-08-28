"""Konnektor-Vertrag und Basisklasse.

Der Vertrag aus Kapitel 5.1 des Konzepts, ausformuliert. Ein Konnektor
beantwortet vier Fragen:

    health()   Geht es der Quelle gut?
    fetch()    Was gibt es seit diesem Cursor Neues?
    normalize() Wie sieht das im kanonischen Schema aus?
    backfill() Wie hole ich einen vergangenen Zeitraum nach?

Alles andere kommt aus dem SDK.
"""

from __future__ import annotations

import enum
import logging
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

import httpx

from argus_connector.config import ConnectorSettings
from argus_connector.dedupe import DedupeKeyBuilder
from argus_connector.metrics import ConnectorMetrics
from argus_connector.ratelimit import AdaptiveRateLimiter, parse_retry_after
from argus_connector.retry import (
    CircuitBreaker,
    ConnectorError,
    ErrorKind,
    RetryPolicy,
    retry_async,
)

logger = logging.getLogger(__name__)


class ConnectorMode(str, enum.Enum):
    POLL = "poll"
    STREAM = "stream"
    WEBHOOK = "webhook"
    BATCH = "batch"


@dataclass(slots=True)
class HealthStatus:
    healthy: bool
    detail: str = ""
    latency_s: float | None = None
    # Versatz zwischen Quellenuhr und Systemuhr. Positiv: die Quelle geht vor.
    clock_skew_s: float | None = None

    @classmethod
    def ok(cls, detail: str = "", **kwargs: Any) -> HealthStatus:
        return cls(True, detail, **kwargs)

    @classmethod
    def failing(cls, detail: str, **kwargs: Any) -> HealthStatus:
        return cls(False, detail, **kwargs)


@dataclass(slots=True)
class RawRecord:
    """Eine Rohnachricht, so wie die Quelle sie geliefert hat.

    `payload` wird unveraendert in den Bronze-Layer geschrieben. Was hier
    ankommt, ist die Wahrheit; alles Weitere ist Interpretation.
    """

    payload: Any
    fetched_at: float = field(default_factory=time.time)
    # Zeitstempel laut Quelle, sofern vorhanden. Grundlage fuer die
    # Lag-Messung und die Uhrendrift.
    source_timestamp: float | None = None
    # Wert, den der Cursor annehmen soll, wenn dieser Satz verarbeitet ist.
    cursor_hint: Any = None
    dedupe_key: str | None = None
    # Verweis ins Bronze-Archiv; wird vom Runner nachgetragen.
    raw_ref: str | None = None


@dataclass(slots=True)
class CanonicalMessage:
    """Eine kanonisierte Nachricht, bereit fuer den Bus."""

    subject_suffix: str
    payload: dict[str, Any]
    dedupe_key: str
    observed_at: float | None = None


@dataclass(slots=True)
class FetchResult:
    """Ergebnis eines Abrufs."""

    records: list[RawRecord] = field(default_factory=list)
    # Cursor nach diesem Batch. None bedeutet: unveraendert lassen.
    next_cursor: Any = None
    # True, wenn die Quelle weitere Daten hat und sofort erneut abgerufen
    # werden soll, statt das Poll-Intervall abzuwarten.
    has_more: bool = False

    def __len__(self) -> int:
        return len(self.records)


@runtime_checkable
class Connector(Protocol):
    """Der Vertrag aus Kapitel 5.1."""

    id: str
    mode: ConnectorMode

    async def health(self) -> HealthStatus: ...
    async def fetch(self, cursor: Any | None) -> FetchResult: ...
    def normalize(self, raw: RawRecord) -> list[CanonicalMessage]: ...
    def backfill(self, start: datetime, end: datetime) -> AsyncIterator[FetchResult]: ...


class BaseConnector:
    """Gemeinsame Grundlage.

    Bringt einen HTTP-Client mit, der Rate-Limiting, Backoff, Circuit Breaker,
    Retry-After-Auswertung und Uhrendrift-Messung bereits erledigt. Ein
    Konnektor ruft `self.get_json(url)` auf und bekommt entweder Daten oder
    eine klassifizierte Ausnahme.
    """

    id: str = "base"
    mode: ConnectorMode = ConnectorMode.POLL
    # Felder, aus denen der dedupe_key gebildet wird. Jeder Konnektor legt sie
    # fest; ohne sie kann das SDK keine Idempotenz zusichern.
    dedupe_fields: Sequence[str] = ()

    def __init__(
        self,
        settings: ConnectorSettings,
        *,
        metrics: ConnectorMetrics | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.id = settings.connector_id
        self.metrics = metrics or ConnectorMetrics(settings.connector_id, settings.source_id)

        self.rate_limiter = AdaptiveRateLimiter(
            requests_per_second=settings.ratelimit.requests_per_second,
            burst=settings.ratelimit.burst,
            backoff_factor=settings.ratelimit.backoff_factor,
            recovery_step=settings.ratelimit.recovery_step,
            recovery_interval_s=settings.ratelimit.recovery_interval_s,
            min_requests_per_second=settings.ratelimit.min_requests_per_second,
            politeness_delay_s=settings.ratelimit.politeness_delay_s,
            on_delay=self.metrics.add_rate_limit_delay,
            on_rate_change=self.metrics.set_rate,
        )
        self.retry_policy = RetryPolicy(
            max_attempts=settings.retry.max_attempts,
            base_delay_s=settings.retry.base_delay_s,
            max_delay_s=settings.retry.max_delay_s,
            jitter=settings.retry.jitter,
        )
        self.breaker = CircuitBreaker(
            failure_threshold=settings.retry.circuit_failure_threshold,
            reset_timeout_s=settings.retry.circuit_reset_timeout_s,
            success_threshold=settings.retry.circuit_success_threshold,
        )
        self.metrics.set_rate(self.rate_limiter.current_rate)

        self._client = client
        self._owns_client = client is None
        self._dedupe: DedupeKeyBuilder | None = (
            DedupeKeyBuilder(settings.source_id, self.dedupe_fields)
            if self.dedupe_fields
            else None
        )
        self.last_clock_skew_s: float | None = None

    # -- HTTP ------------------------------------------------------------

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.settings.fetch_timeout_s, connect=10.0),
                follow_redirects=True,
                headers={
                    # Identifizierender User-Agent: Kapitel 14 verlangt, dass
                    # ein Betreiber erkennen kann, wer da abruft.
                    "User-Agent": (
                        f"ARGUS/{self.settings.connector_version} "
                        f"({self.settings.connector_id}; +https://github.com/argus)"
                    ),
                    "Accept-Encoding": "gzip, deflate",
                },
            )
        return self._client

    @staticmethod
    def _retry_after_from(exc: BaseException) -> float | None:
        if isinstance(exc, httpx.HTTPStatusError):
            return parse_retry_after(exc.response.headers.get("Retry-After"))
        return None

    def _record_clock_skew(self, response: httpx.Response) -> None:
        """Misst den Versatz zwischen Quellenuhr und Systemuhr.

        Der Date-Header ist sekundengenau und enthaelt die Laufzeit der Antwort;
        fuer die Frage "geht die Uhr der Quelle um Minuten falsch" reicht das
        vollkommen, und genau das ist die Frage.
        """
        date_header = response.headers.get("Date")
        if not date_header:
            return
        import email.utils

        try:
            parsed = email.utils.parsedate_to_datetime(date_header)
        except (TypeError, ValueError):
            return
        if parsed is None:
            return
        skew = parsed.timestamp() - time.time()
        self.last_clock_skew_s = skew
        self.metrics.set_clock_skew(skew)
        if abs(skew) > self.settings.max_clock_skew_s:
            self.metrics.error(ErrorKind.CLOCK_SKEW.value)
            logger.warning(
                "Uhrendrift zu %s betraegt %.1f s (Grenze %.0f s). Zeitstempel "
                "dieser Quelle sind mit Vorsicht zu behandeln.",
                self.settings.source_id, skew, self.settings.max_clock_skew_s,
            )

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Ein HTTP-Aufruf mit allem, was dazugehoert."""

        async def attempt() -> httpx.Response:
            await self.rate_limiter.acquire()
            with self.metrics.fetch_timer():
                response = await self.client.request(method, url, **kwargs)
            self._record_clock_skew(response)

            if response.status_code == 429:
                retry_after = parse_retry_after(response.headers.get("Retry-After"))
                self.rate_limiter.on_throttled(retry_after)
                self.metrics.error(ErrorKind.RATE_LIMITED.value)
                response.raise_for_status()
            elif response.status_code == 503:
                # 503 mit Retry-After ist eine Drosselung mit anderem Namen.
                retry_after = parse_retry_after(response.headers.get("Retry-After"))
                if retry_after is not None:
                    self.rate_limiter.on_throttled(retry_after)
                response.raise_for_status()
            else:
                response.raise_for_status()

            self.rate_limiter.on_success()
            return response

        def on_error(kind: ErrorKind, attempt_no: int, delay: float) -> None:
            self.metrics.error(kind.value)

        response = await retry_async(
            attempt,
            policy=self.retry_policy,
            breaker=self.breaker,
            on_error=on_error,
            retry_after_hint=self._retry_after_from,
        )
        self.metrics.set_circuit_state(self.breaker.state.value)
        return response

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        """GET mit JSON-Antwort. Behandelt leere und ungueltige Antworten."""
        response = await self.request("GET", url, **kwargs)
        if not response.content:
            raise ConnectorError(
                f"Leere Antwort von {url}", kind=ErrorKind.EMPTY_RESPONSE
            )
        try:
            return response.json()
        except ValueError as exc:
            preview = response.text[:200]
            raise ConnectorError(
                f"Antwort von {url} ist kein gueltiges JSON: {exc}. Anfang: {preview!r}",
                kind=ErrorKind.INVALID_PAYLOAD,
            ) from exc

    # -- Vertrag ---------------------------------------------------------

    async def health(self) -> HealthStatus:
        return HealthStatus.ok("kein eigener Health-Check umgesetzt")

    async def fetch(self, cursor: Any | None) -> FetchResult:
        raise NotImplementedError("fetch() muss der Konnektor umsetzen")

    def normalize(self, raw: RawRecord) -> list[CanonicalMessage]:
        raise NotImplementedError("normalize() muss der Konnektor umsetzen")

    async def backfill(self, start: datetime, end: datetime) -> AsyncIterator[FetchResult]:
        """Standardumsetzung: kein Backfill.

        Quellen ohne historischen Zugriff sind der Normalfall; Konnektoren mit
        Archiv ueberschreiben die Methode.
        """
        raise NotImplementedError(
            f"{self.id} unterstuetzt keinen Backfill. Historische Daten muessen "
            "aus dem Bronze-Layer wiederhergestellt werden."
        )
        yield  # pragma: no cover - macht die Methode zum AsyncIterator

    # -- Hilfen fuer Konnektoren ----------------------------------------

    def dedupe_key_for(self, record: Any) -> str:
        if self._dedupe is None:
            raise RuntimeError(
                f"{self.id} hat keine dedupe_fields gesetzt. Ohne sie kann das SDK "
                "keine Idempotenz zusichern - Kapitel 5.2 verlangt sie."
            )
        return self._dedupe.build(record)

    @staticmethod
    def to_epoch(value: str | float | datetime | None) -> float | None:
        """Duldsamer Zeitstempel-Parser fuer Quellen mit wechselnden Formaten."""
        if value is None:
            return None
        if isinstance(value, int | float):
            # Millisekunden erkennen: alles ueber dem Jahr 5138 in Sekunden ist
            # mit hoher Sicherheit eine Millisekundenangabe.
            return float(value) / 1000.0 if value > 1e11 else float(value)
        if isinstance(value, datetime):
            dt = value if value.tzinfo else value.replace(tzinfo=UTC)
            return dt.timestamp()
        text = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.timestamp()

    @staticmethod
    def to_iso(value: str | float | datetime | None) -> str | None:
        """Gegenstueck zu to_epoch: UTC-Zeitstempel nach RFC 3339.

        ARGUS transportiert Zeiten ausschliesslich als UTC-Zeichenkette mit
        Zonenangabe. Ein Konnektor, der eine Quellzeit weiterreicht, geht immer
        durch diese Funktion - dann kann kein Format durchrutschen.
        """
        epoch = BaseConnector.to_epoch(value)
        if epoch is None:
            return None
        return datetime.fromtimestamp(epoch, tz=UTC).isoformat().replace("+00:00", "Z")

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None
