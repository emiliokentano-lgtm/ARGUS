"""Wiederholung, Backoff und Circuit Breaker.

Die Fehlerklassifikation ist der eigentliche Inhalt: was sich wiederholen
laesst und was nicht. Ein 404 wiederholt man nicht, ein 503 schon, und ein
TLS-Fehler ist etwas anderes als ein DNS-Fehler - auch wenn beide "geht nicht"
bedeuten.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ErrorKind(str, enum.Enum):
    """Fehlerklassen. Sie landen als Label in connector_errors_total und
    entscheiden, ob wiederholt wird."""

    DNS = "dns"
    TLS = "tls"
    CONNECT = "connect"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"      # HTTP 429
    SERVER_ERROR = "server_error"      # HTTP 5xx
    CLIENT_ERROR = "client_error"      # HTTP 4xx ausser 429
    EMPTY_RESPONSE = "empty_response"
    INVALID_PAYLOAD = "invalid_payload"
    SCHEMA_DRIFT = "schema_drift"
    BUS_UNAVAILABLE = "bus_unavailable"
    STORAGE_UNAVAILABLE = "storage_unavailable"
    CURSOR_UNAVAILABLE = "cursor_unavailable"
    CLOCK_SKEW = "clock_skew"
    UNKNOWN = "unknown"


# Wiederholbar: der Fehler kann beim naechsten Versuch weg sein.
RETRYABLE = frozenset(
    {
        ErrorKind.DNS,
        ErrorKind.CONNECT,
        ErrorKind.TIMEOUT,
        ErrorKind.RATE_LIMITED,
        ErrorKind.SERVER_ERROR,
        ErrorKind.EMPTY_RESPONSE,
        ErrorKind.BUS_UNAVAILABLE,
        ErrorKind.STORAGE_UNAVAILABLE,
        ErrorKind.CURSOR_UNAVAILABLE,
    }
)


class ConnectorError(Exception):
    """Basisfehler mit Klassifikation."""

    kind: ErrorKind = ErrorKind.UNKNOWN

    def __init__(self, message: str, *, kind: ErrorKind | None = None) -> None:
        super().__init__(message)
        if kind is not None:
            self.kind = kind

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE


class TransientError(ConnectorError):
    kind = ErrorKind.UNKNOWN


class PermanentError(ConnectorError):
    kind = ErrorKind.CLIENT_ERROR


class CircuitOpen(ConnectorError):
    """Der Circuit Breaker laesst gerade keine Anfragen durch."""

    kind = ErrorKind.CONNECT

    def __init__(self, retry_after_s: float) -> None:
        super().__init__(
            f"Circuit Breaker offen, naechster Versuch in {retry_after_s:.1f} s"
        )
        self.retry_after_s = retry_after_s


def classify(exc: BaseException) -> ErrorKind:
    """Ordnet eine Ausnahme einer Fehlerklasse zu.

    httpx unterscheidet die Transportfehler feiner, als man auf den ersten
    Blick meint - und die Unterscheidung ist im Betrieb Gold wert: ein
    DNS-Fehler heisst "Konfiguration oder Netz", ein TLS-Fehler heisst
    "Zertifikat oder Proxy", ein Timeout heisst "die Quelle ist ueberlastet".
    """
    if isinstance(exc, ConnectorError):
        return exc.kind
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return ErrorKind.RATE_LIMITED
        if 500 <= status < 600:
            return ErrorKind.SERVER_ERROR
        return ErrorKind.CLIENT_ERROR
    if isinstance(exc, httpx.ConnectTimeout | httpx.ReadTimeout | httpx.WriteTimeout | httpx.PoolTimeout):
        return ErrorKind.TIMEOUT
    # Muss vor ConnectError geprueft werden: ConnectError ist die Oberklasse.
    if isinstance(exc, httpx.ConnectError):
        text = str(exc).lower()
        if "name or service not known" in text or "nodename nor servname" in text \
                or "temporary failure in name resolution" in text or "getaddrinfo" in text:
            return ErrorKind.DNS
        if "certificate" in text or "ssl" in text or "tls" in text:
            return ErrorKind.TLS
        return ErrorKind.CONNECT
    if isinstance(exc, httpx.TransportError):
        return ErrorKind.CONNECT
    if isinstance(exc, ValueError):
        # json.JSONDecodeError ist eine ValueError.
        return ErrorKind.INVALID_PAYLOAD
    if isinstance(exc, asyncio.TimeoutError | TimeoutError):
        return ErrorKind.TIMEOUT
    if isinstance(exc, OSError):
        return ErrorKind.CONNECT
    return ErrorKind.UNKNOWN


def is_retryable(exc: BaseException) -> bool:
    return classify(exc) in RETRYABLE


@dataclass(slots=True)
class RetryPolicy:
    """Exponentieller Backoff mit vollem Jitter."""

    max_attempts: int = 5
    base_delay_s: float = 0.5
    max_delay_s: float = 60.0
    jitter: bool = True

    def delay_for(self, attempt: int, *, rng: random.Random | None = None) -> float:
        """Wartezeit vor Versuch `attempt` (1-basiert).

        Voller Jitter statt "exponentiell plus etwas Rauschen": bei einem
        Ausfall, der viele Konnektoren gleichzeitig trifft, verteilt nur der
        volle Jitter die Wiederkehr wirklich gleichmaessig. Sonst kommen alle
        im selben Moment zurueck und legen die gerade erholte Quelle erneut um.
        """
        if attempt < 1:
            raise ValueError("attempt ist 1-basiert")
        ceiling = min(self.max_delay_s, self.base_delay_s * (2 ** (attempt - 1)))
        if not self.jitter:
            return ceiling
        return (rng or random).uniform(0.0, ceiling)


class CircuitState(str, enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Schuetzt eine kranke Quelle davor, weiter angefragt zu werden.

    Ohne ihn hämmert ein Konnektor gegen eine ausgefallene Quelle, verbrennt
    Rate-Limit-Kontingent und verstopft die eigenen Protokolle. Nach
    `failure_threshold` aufeinanderfolgenden Fehlern oeffnet der Kreis; nach
    `reset_timeout_s` laesst er einen Testabruf durch (halb offen) und
    schliesst erst nach `success_threshold` Erfolgen wieder.
    """

    failure_threshold: int = 5
    reset_timeout_s: float = 60.0
    success_threshold: int = 2
    clock: Callable[[], float] = time.monotonic

    state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    failures: int = field(default=0, init=False)
    successes: int = field(default=0, init=False)
    opened_at: float | None = field(default=None, init=False)

    def _retry_after(self) -> float:
        if self.opened_at is None:
            return 0.0
        return max(0.0, self.reset_timeout_s - (self.clock() - self.opened_at))

    def before_request(self) -> None:
        """Wirft CircuitOpen, wenn gerade nichts durchgelassen wird."""
        if self.state is CircuitState.OPEN:
            remaining = self._retry_after()
            if remaining > 0:
                raise CircuitOpen(remaining)
            # Schonfrist abgelaufen: einen Testabruf zulassen.
            self.state = CircuitState.HALF_OPEN
            self.successes = 0
            logger.info("Circuit Breaker halb offen - Testabruf")

    def on_success(self) -> None:
        if self.state is CircuitState.HALF_OPEN:
            self.successes += 1
            if self.successes >= self.success_threshold:
                logger.info("Circuit Breaker geschlossen - Quelle antwortet wieder")
                self.state = CircuitState.CLOSED
                self.failures = 0
                self.opened_at = None
            return
        self.failures = 0

    def on_failure(self) -> None:
        if self.state is CircuitState.HALF_OPEN:
            # Der Testabruf ist gescheitert: sofort wieder zu, Frist neu.
            logger.warning("Circuit Breaker wieder offen - Testabruf gescheitert")
            self.state = CircuitState.OPEN
            self.opened_at = self.clock()
            self.successes = 0
            return
        self.failures += 1
        if self.failures >= self.failure_threshold:
            logger.warning(
                "Circuit Breaker offen nach %d Fehlern - Pause %.0f s",
                self.failures, self.reset_timeout_s,
            )
            self.state = CircuitState.OPEN
            self.opened_at = self.clock()


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy,
    breaker: CircuitBreaker | None = None,
    on_error: Callable[[ErrorKind, int, float], None] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rng: random.Random | None = None,
    retry_after_hint: Callable[[BaseException], float | None] | None = None,
) -> T:
    """Fuehrt `operation` aus und wiederholt sie bei wiederholbaren Fehlern.

    `retry_after_hint` erlaubt es, eine von der Quelle vorgegebene Wartezeit
    (Retry-After) dem berechneten Backoff vorzuziehen - die Quelle weiss
    besser, wann sie wieder kann.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, policy.max_attempts + 1):
        if breaker is not None:
            breaker.before_request()
        try:
            result = await operation()
        except BaseException as exc:  # noqa: BLE001 - wird klassifiziert und weitergereicht
            if isinstance(exc, asyncio.CancelledError):
                raise
            kind = classify(exc)
            last_exc = exc
            retryable = kind in RETRYABLE
            if breaker is not None and kind is not ErrorKind.CLIENT_ERROR:
                breaker.on_failure()

            if not retryable or attempt >= policy.max_attempts:
                if on_error is not None:
                    on_error(kind, attempt, 0.0)
                raise

            delay = policy.delay_for(attempt, rng=rng)
            if retry_after_hint is not None:
                hinted = retry_after_hint(exc)
                if hinted is not None:
                    delay = max(delay, hinted)
            if on_error is not None:
                on_error(kind, attempt, delay)
            logger.warning(
                "Versuch %d/%d fehlgeschlagen (%s), erneut in %.2f s: %s",
                attempt, policy.max_attempts, kind.value, delay, exc,
            )
            await sleep(delay)
        else:
            if breaker is not None:
                breaker.on_success()
            return result

    assert last_exc is not None
    raise last_exc
