"""Rate-Limiting mit Token-Bucket und adaptiver Drosselung.

Zwei Aufgaben, die oft verwechselt werden:

* Das konfigurierte Limit einhalten, damit die Quelle nicht ueberlastet wird
  und ihre Nutzungsbedingungen gewahrt bleiben (Kapitel 14).
* Auf ein *gemeldetes* Limit reagieren, wenn die Quelle trotzdem 429 sagt -
  weil sie strenger ist als dokumentiert, weil andere Verbraucher mitzaehlen,
  oder weil das Kontingent geteilt wird.
"""

from __future__ import annotations

import asyncio
import email.utils
import logging
import time
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

# Fliesskomma-Toleranz beim Vergleich von Tokens.
#
# Ohne sie dreht acquire() endlos: nach dem Warten liefert
# elapsed * rate wegen der Rundung 0.9999999999999 statt 1.0 Token, der
# Vergleich schlaegt fehl, die naechste berechnete Wartezeit liegt bei 1e-13
# und aendert die Uhr nicht mehr. Im Betrieb waere das eine Schleife, die die
# Ereignisschleife belegt, ohne dass jemals eine Anfrage durchgeht.
_TOKEN_EPSILON = 1e-9

# Untergrenze fuer eine Wartezeit. Verhindert Sleeps unterhalb der
# Uhrenaufloesung, die keinen Fortschritt bringen.
_MIN_SLEEP_S = 1e-4


class TokenBucket:
    """Klassischer Token-Bucket.

    Tokens fliessen mit `rate` pro Sekunde nach, hoechstens `burst` sammeln
    sich an. `acquire()` wartet, bis genug da sind.
    """

    def __init__(
        self,
        rate: float,
        burst: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate muss groesser als 0 sein")
        if burst < 1:
            raise ValueError("burst muss mindestens 1 sein")
        self._rate = float(rate)
        self._burst = int(burst)
        self._tokens = float(burst)
        self._clock = clock
        self._sleep = sleep
        self._updated = clock()
        self._lock = asyncio.Lock()

    @property
    def rate(self) -> float:
        return self._rate

    def set_rate(self, rate: float) -> None:
        """Aendert die Rate zur Laufzeit. Der Vorrat wird auf den neuen
        Eimer begrenzt, damit eine Drosselung sofort wirkt und nicht erst,
        wenn der alte Vorrat aufgebraucht ist."""
        self._refill()
        self._rate = max(rate, 1e-9)
        self._tokens = min(self._tokens, float(self._burst))

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._updated
        if elapsed > 0:
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._updated = now

    async def acquire(self, tokens: float = 1.0) -> float:
        """Wartet, bis `tokens` verfuegbar sind. Gibt die Wartezeit zurueck."""
        if tokens > self._burst:
            raise ValueError(f"{tokens} Tokens angefordert, aber der Eimer fasst nur {self._burst}")
        waited = 0.0
        async with self._lock:
            while True:
                self._refill()
                if self._tokens >= tokens - _TOKEN_EPSILON:
                    self._tokens = max(0.0, self._tokens - tokens)
                    return waited
                deficit = tokens - self._tokens
                wait = max(deficit / self._rate, _MIN_SLEEP_S)
                waited += wait
                await self._sleep(wait)


def parse_retry_after(value: str | None, *, now: float | None = None) -> float | None:
    """Liest den Retry-After-Header.

    Erlaubt sind zwei Formen: Sekunden als Ganzzahl oder ein HTTP-Datum. Beide
    kommen in freier Wildbahn vor, und wer nur die erste unterstuetzt, ignoriert
    die Haelfte der Hinweise.
    """
    if not value:
        return None
    value = value.strip()
    try:
        seconds = float(value)
    except ValueError:
        pass
    else:
        return max(0.0, seconds)

    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    target = parsed.timestamp()
    reference = now if now is not None else time.time()
    return max(0.0, target - reference)


class AdaptiveRateLimiter:
    """Token-Bucket, der auf HTTP 429 reagiert.

    Multiplikative Verringerung, additive Erholung - dasselbe Muster wie bei
    der Ueberlastregelung in TCP und aus demselben Grund: schnell nachgeben,
    langsam wieder zugreifen. Wer nach einem 429 sofort wieder auf volle Rate
    geht, bekommt den naechsten 429.
    """

    def __init__(
        self,
        *,
        requests_per_second: float,
        burst: int,
        backoff_factor: float = 0.5,
        recovery_step: float = 0.1,
        recovery_interval_s: float = 30.0,
        min_requests_per_second: float = 0.1,
        politeness_delay_s: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        on_delay: Callable[[float], None] | None = None,
        on_rate_change: Callable[[float], None] | None = None,
    ) -> None:
        self._configured_rate = float(requests_per_second)
        self._min_rate = float(min_requests_per_second)
        self._backoff_factor = float(backoff_factor)
        self._recovery_step = float(recovery_step)
        self._recovery_interval_s = float(recovery_interval_s)
        self._politeness_delay_s = float(politeness_delay_s)
        self._clock = clock
        self._sleep = sleep
        self._on_delay = on_delay
        self._on_rate_change = on_rate_change

        self._bucket = TokenBucket(requests_per_second, burst, clock=clock, sleep=sleep)
        self._last_recovery = clock()
        self._last_request: float | None = None
        # Absolute Zeit, bis zu der auf Anweisung der Quelle pausiert wird.
        self._paused_until: float | None = None
        self._throttle_events = 0

    @property
    def current_rate(self) -> float:
        return self._bucket.rate

    @property
    def configured_rate(self) -> float:
        return self._configured_rate

    @property
    def throttle_events(self) -> int:
        return self._throttle_events

    def _set_rate(self, rate: float) -> None:
        rate = max(self._min_rate, min(self._configured_rate, rate))
        if abs(rate - self._bucket.rate) < 1e-12:
            return
        self._bucket.set_rate(rate)
        if self._on_rate_change is not None:
            self._on_rate_change(rate)

    def _maybe_recover(self) -> None:
        """Erholt die Rate schrittweise, wenn laenger kein 429 kam."""
        if self._bucket.rate >= self._configured_rate:
            return
        now = self._clock()
        if now - self._last_recovery < self._recovery_interval_s:
            return
        self._last_recovery = now
        self._set_rate(self._bucket.rate + self._configured_rate * self._recovery_step)
        logger.info("Rate erholt auf %.3f/s", self._bucket.rate)

    async def acquire(self) -> float:
        """Wartet, bis eine Anfrage erlaubt ist. Gibt die Wartezeit zurueck."""
        waited = 0.0

        # 1. Von der Quelle angeordnete Pause (Retry-After).
        if self._paused_until is not None:
            remaining = self._paused_until - self._clock()
            if remaining > 0:
                waited += remaining
                await self._sleep(remaining)
            self._paused_until = None

        self._maybe_recover()

        # 2. Hoeflichkeitsverzoegerung zwischen zwei Abrufen.
        if self._politeness_delay_s > 0 and self._last_request is not None:
            gap = self._clock() - self._last_request
            if gap < self._politeness_delay_s:
                pause = self._politeness_delay_s - gap
                waited += pause
                await self._sleep(pause)

        # 3. Token-Bucket.
        waited += await self._bucket.acquire()
        self._last_request = self._clock()

        if waited > 0 and self._on_delay is not None:
            self._on_delay(waited)
        return waited

    def on_throttled(self, retry_after_s: float | None = None) -> None:
        """Von der Quelle gedrosselt (HTTP 429 oder 503 mit Retry-After)."""
        self._throttle_events += 1
        self._set_rate(self._bucket.rate * self._backoff_factor)
        self._last_recovery = self._clock()
        if retry_after_s is not None and retry_after_s > 0:
            self._paused_until = self._clock() + retry_after_s
            logger.warning(
                "Gedrosselt: Rate auf %.3f/s, Pause %.1f s laut Retry-After",
                self._bucket.rate,
                retry_after_s,
            )
        else:
            logger.warning("Gedrosselt: Rate auf %.3f/s", self._bucket.rate)

    def on_success(self) -> None:
        self._maybe_recover()
