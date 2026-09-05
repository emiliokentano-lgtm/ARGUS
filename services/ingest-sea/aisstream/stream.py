"""WebSocket-Verbindung zu AISStream.

Eine dauerhafte Verbindung, die sich selbst wiederherstellt, und eine
Warteschlange, aus der die Verarbeitung Stapel entnimmt. Der Leser laeuft als
eigene Aufgabe und blockiert nie - das ist die zentrale Entwurfsentscheidung
dieses Moduls, und der Grund steht bei `queue_size` in config.py.

DREI DINGE, DIE HIER SCHIEFGEHEN UND DIE MAN UNTERSCHEIDEN MUSS
---------------------------------------------------------------
1. Die Leitung bricht ab (kein Close-Frame, TCP-Reset, Zwischenknoten weg).
   Das ist der Normalfall im Betrieb. Antwort: neu verbinden, Abonnement neu
   aufbauen, weiterlaufen.
2. Der Dienst weist uns ab (ungueltiger API-Schluessel). Das ist ein
   dauerhafter Zustand. Antwort: aufhoeren. Ein Konnektor, der sich im
   Sekundentakt mit falschem Schluessel wieder anmeldet, ist genau das
   Verhalten, das Kapitel 14 verbietet - und er wird zu Recht gesperrt.
3. Die Leitung steht, aber es kommt nichts. Sieht aus wie 'ruhige See' und
   ist meistens ein verlorenes Abonnement. Antwort: nach `idle_timeout_s`
   behandeln wie Fall 1.

Fall 2 von Fall 1 zu trennen ist der eigentliche Wert dieses Moduls.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatus

from aisstream.config import AisStreamSettings

logger = logging.getLogger(__name__)

# Zeichenketten, mit denen AISStream eine Abweisung begruendet. Der Dienst
# schickt sie als gewoehnliche Textnachricht, nicht als Close-Code - deshalb
# muss der Text geprueft werden. Die Liste ist bewusst kurz und wird eher zu
# selten als zu haeufig treffen: eine Fehlklassifikation in Richtung
# "dauerhaft" wuerde einen gesunden Konnektor stilllegen.
_FATAL_MARKERS = (
    "invalid api key",
    "apikey is invalid",
    "invalid apikey",
    "unauthorized",
    "authentication failed",
)


class FatalStreamError(RuntimeError):
    """Ein Zustand, den kein Wiederholungsversuch behebt.

    Falscher Schluessel, gesperrtes Konto, abgelehnte Abonnementform. Der
    Konnektor haelt an und meldet sich krank, statt weiter anzuklopfen.
    """


ConnectFactory = Callable[..., Any]


class AisStreamClient:
    """Haelt die Verbindung und fuellt die Warteschlange."""

    def __init__(
        self,
        settings: AisStreamSettings,
        *,
        connect: ConnectFactory | None = None,
        clock: Callable[[], float] = time.monotonic,
        on_reconnect: Callable[[int, float], None] | None = None,
        on_drop: Callable[[int], None] | None = None,
    ) -> None:
        self.settings = settings
        # Einspeisbar, damit die Tests einen echten Verbindungsabbruch
        # ausloesen koennen, ohne dass ein Netz im Spiel ist.
        self._connect = connect or websockets.connect
        self._clock = clock
        # Oeffentlich, damit ein eingespeister Client sie nachtraeglich bekommt.
        # Sie nur im Konstruktor zu setzen hiesse: wer den Client selbst baut -
        # jeder Test -, laeuft ohne Metriken, und genau die sollen geprueft
        # werden.
        self.on_reconnect = on_reconnect
        self.on_drop = on_drop

        self._queue: deque[dict[str, Any]] = deque()
        self._nonempty = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

        self.connected = False
        self.connection_attempts = 0
        self.successful_connections = 0
        self.messages_received = 0
        self.messages_dropped = 0
        self.last_message_at: float | None = None
        self.last_connected_at: float | None = None
        self.last_disconnected_at: float | None = None
        self.fatal: FatalStreamError | None = None

    # -- Lebenszyklus -----------------------------------------------------

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping.clear()
            self._task = asyncio.create_task(self._run(), name="aisstream-reader")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self.connected = False

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    # -- Warteschlange ----------------------------------------------------

    def _offer(self, message: dict[str, Any]) -> None:
        """Legt eine Nachricht ab, ohne je zu blockieren.

        Laeuft die Warteschlange ueber, faellt die AELTESTE Nachricht heraus.
        Bei einer Live-Quelle ohne Replay ist das die richtige Wahl: die
        neueste Position eines Schiffes ist mehr wert als die uebernaechste
        alte. Verlust bleibt Verlust - er wird gezaehlt und protokolliert,
        nicht verschwiegen (Prinzip 4).
        """
        if len(self._queue) >= self.settings.queue_size:
            self._queue.popleft()
            self.messages_dropped += 1
            if self.on_drop is not None:
                self.on_drop(1)
            if self.messages_dropped % 10_000 == 1:
                logger.warning(
                    "Rueckstau: Warteschlange (%d) voll, %d Nachrichten verworfen. "
                    "Die Verarbeitung kommt nicht nach - das ist Datenverlust, "
                    "keine Drosselung.",
                    self.settings.queue_size,
                    self.messages_dropped,
                )
        self._queue.append(message)
        self._nonempty.set()

    async def batch(self, *, max_size: int, max_wait_s: float) -> list[dict[str, Any]]:
        """Entnimmt bis zu `max_size` Nachrichten.

        Wartet hoechstens `max_wait_s` auf die erste; danach wird
        zusammengerafft, was ohne weiteres Warten da ist. Ein Stapel ist
        deshalb bei ruhiger Quelle klein und bei Last gross, ohne dass
        irgendwo eine Heuristik entscheidet.
        """
        if self.fatal is not None:
            raise self.fatal

        if not self._queue:
            try:
                await asyncio.wait_for(self._nonempty.wait(), timeout=max_wait_s)
            except TimeoutError:
                return []

        batch: list[dict[str, Any]] = []
        while self._queue and len(batch) < max_size:
            batch.append(self._queue.popleft())
        if not self._queue:
            self._nonempty.clear()
        return batch

    @property
    def pending(self) -> int:
        return len(self._queue)

    # -- Leser ------------------------------------------------------------

    async def _run(self) -> None:
        attempt = 0
        while not self._stopping.is_set():
            self.connection_attempts += 1
            try:
                await self._session()
                # Sauber beendet (Close-Frame): kein Fehler, aber auch kein
                # Grund zu warten - direkt neu verbinden.
                attempt = 0
            except FatalStreamError as exc:
                self.fatal = exc
                self.connected = False
                logger.error(
                    "AISStream weist die Verbindung dauerhaft ab: %s. "
                    "Der Konnektor versucht es NICHT erneut.",
                    exc,
                )
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - jeder Abbruch ist behandelbar
                self.connected = False
                self.last_disconnected_at = self._clock()
                attempt += 1
                if 0 <= self.settings.reconnect_max_attempts < attempt:
                    self.fatal = FatalStreamError(
                        f"Nach {attempt} Versuchen keine Verbindung: {exc}"
                    )
                    return
                delay = self._backoff(attempt)
                logger.warning(
                    "Verbindung zu AISStream verloren (%s: %s). Versuch %d in %.1f s.",
                    type(exc).__name__,
                    exc,
                    attempt,
                    delay,
                )
                if self.on_reconnect is not None:
                    self.on_reconnect(attempt, delay)
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stopping.wait(), timeout=delay)

    def _backoff(self, attempt: int) -> float:
        """Exponentiell mit vollem Jitter, gedeckelt.

        Voller Jitter statt fester Verdopplung: fallen viele Konnektoren
        gleichzeitig aus - etwa weil der Dienst neu startet -, kommen sie
        sonst im Gleichtakt zurueck und legen ihn erneut um.
        """
        ceiling = min(
            self.settings.reconnect_max_delay_s,
            self.settings.reconnect_base_delay_s * (2 ** (attempt - 1)),
        )
        return random.uniform(0.0, ceiling)  # noqa: S311 - Backoff, keine Kryptografie

    async def _session(self) -> None:
        """Eine Verbindung von Aufbau bis Abbruch."""
        try:
            connection = await asyncio.wait_for(
                self._connect(
                    self.settings.url,
                    ping_interval=self.settings.ping_interval_s,
                    ping_timeout=self.settings.ping_timeout_s,
                    max_size=2**20,
                ),
                timeout=self.settings.connect_timeout_s,
            )
        except InvalidStatus as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (401, 403):
                raise FatalStreamError(
                    f"AISStream lehnt den Handschlag mit HTTP {status} ab. "
                    "Das ist ein Schluessel- oder Kontoproblem, kein Netzfehler."
                ) from exc
            raise

        async with _closing(connection):
            # Das Abonnement wird nach JEDER Verbindung neu gesendet
            # (Aufgabenstellung, Constraint 1). AISStream haelt es nicht
            # ueber einen Abbruch hinweg.
            await connection.send(json.dumps(self.settings.subscription()))
            self.connected = True
            self.successful_connections += 1
            self.last_connected_at = self._clock()
            logger.info(
                "Mit AISStream verbunden, Abonnement gesendet: %s",
                json.dumps(self.settings.redacted_subscription(), ensure_ascii=False),
            )
            await self._read(connection)

    async def _read(self, connection: Any) -> None:
        idle = self.settings.idle_timeout_s
        while not self._stopping.is_set():
            try:
                raw = await asyncio.wait_for(connection.recv(), timeout=idle)
            except TimeoutError as exc:
                # Kein Fehler auf der Leitung, aber auch keine Daten. Fuer
                # eine Quelle, die im Sekundentakt sendet, ist Stille das
                # verlaesslichere Ausfallsignal als ein fehlendes Pong.
                raise ConnectionError(
                    f"Seit {idle:.0f} s keine Nachricht. Verbindung gilt als tot."
                ) from exc
            except ConnectionClosed:
                raise

            message = self._decode(raw)
            if message is None:
                continue
            self.messages_received += 1
            self.last_message_at = self._clock()
            self._offer(message)

    def _decode(self, raw: str | bytes) -> dict[str, Any] | None:
        """JSON-Nachricht oder Fehlermeldung des Dienstes.

        AISStream meldet Probleme als gewoehnliche Nachricht mit einem
        `error`-Feld, nicht ueber den Close-Code. Genau hier entscheidet sich
        Fall 2 gegen Fall 1.
        """
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError):
            preview = raw[:200] if isinstance(raw, str) else raw[:200].decode("utf-8", "replace")
            logger.warning("Nachricht ist kein JSON, uebersprungen: %r", preview)
            return None
        if not isinstance(decoded, dict):
            return None

        error = decoded.get("error") or decoded.get("Error")
        if isinstance(error, str) and error:
            lowered = error.lower()
            if any(marker in lowered for marker in _FATAL_MARKERS):
                raise FatalStreamError(error)
            logger.warning("AISStream meldet einen Fehler: %s", error)
            return None
        return decoded


@contextlib.asynccontextmanager
async def _closing(connection: Any) -> AsyncIterator[Any]:
    """Schliesst die Verbindung auch dann, wenn der Leser eine Ausnahme wirft.

    `websockets.connect` ist als Kontextmanager gedacht; hier wird es
    schrittweise benutzt, damit der Handschlag ein eigenes Zeitlimit bekommt.
    Das Schliessen darf darueber nicht verlorengehen.
    """
    try:
        yield connection
    finally:
        with contextlib.suppress(Exception):
            await connection.close()
