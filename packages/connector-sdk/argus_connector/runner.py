"""Prozess-Lebenszyklus eines Konnektors.

Der Runner verdrahtet Konnektor, Cursor, Bronze, Bus, Metriken und
Drift-Erkennung und macht daraus einen Prozess, der sich im Betrieb benimmt:

* Er faehrt bei SIGTERM/SIGINT sauber herunter - laufender Batch zu Ende,
  Bronze geschrieben, Cursor festgeschrieben, dann erst beenden.
* Er laesst sich zur Laufzeit ueber NATS anhalten und weiterlaufen lassen
  (Kill-Switch, Kapitel 5.2), ohne Neustart.
* Er schreibt den Cursor erst NACH der bestaetigten Zustellung fest.

Die Reihenfolge im Batch ist der ganze Punkt:

    1. fetch          Daten holen
    2. begin(cursor)  Absicht festhalten
    3. bronze         Rohdaten archivieren
    4. normalize      kanonisieren
    5. publish        veroeffentlichen und Bestaetigung abwarten
    6. commit         Cursor festschreiben

Ein Absturz zwischen 1 und 6 wiederholt den Batch. Doppelte Nachrichten sind
erlaubt und ueber den dedupe_key erkennbar; verlorene sind es nicht.
"""

from __future__ import annotations

import asyncio
import contextlib
import enum
import json
import logging
import signal
import time
from collections.abc import Callable
from typing import Any

from argus_connector.base import BaseConnector, CanonicalMessage, FetchResult
from argus_connector.bronze import BronzeWriter
from argus_connector.bus import Publisher
from argus_connector.config import ConnectorSettings
from argus_connector.cursor import CursorManager, CursorStore
from argus_connector.drift import SchemaDriftDetector
from argus_connector.metrics import ConnectorMetrics
from argus_connector.retry import ConnectorError, ErrorKind, classify

logger = logging.getLogger(__name__)


class RunnerState(str, enum.Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"      # ueber den Kill-Switch angehalten
    STOPPING = "stopping"
    STOPPED = "stopped"


class ConnectorRunner:
    """Fuehrt einen Konnektor aus."""

    def __init__(
        self,
        connector: BaseConnector,
        *,
        settings: ConnectorSettings,
        cursor_store: CursorStore,
        publisher: Publisher,
        bronze: BronzeWriter | None = None,
        metrics: ConnectorMetrics | None = None,
        drift_detector: SchemaDriftDetector | None = None,
        control_subscriber: Any = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.connector = connector
        self.settings = settings
        self.publisher = publisher
        self.bronze = bronze
        self.metrics = metrics or connector.metrics
        self.drift = drift_detector or SchemaDriftDetector()
        self.cursors = CursorManager(cursor_store, settings.connector_id)
        self._cursor_store = cursor_store
        self._control_subscriber = control_subscriber
        self._clock = clock

        self.state = RunnerState.CREATED
        self._stop_event = asyncio.Event()
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._current_batch_lock = asyncio.Lock()

        self.batches_completed = 0
        self.records_processed = 0
        self.messages_published = 0
        self.duplicates_skipped = 0

    # -- Signale und Kill-Switch -----------------------------------------

    def install_signal_handlers(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """SIGTERM und SIGINT loesen ein sauberes Herunterfahren aus.

        Ohne das beendet der Container-Runtime-Kill den Prozess mitten im
        Batch: Bronze-Puffer weg, Cursor auf altem Stand, beim Neustart alles
        noch einmal. Mit ihm wird der laufende Batch zu Ende gefuehrt.
        """
        loop = loop or asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError, ValueError):
                loop.add_signal_handler(sig, self._on_signal, sig)

    def _on_signal(self, sig: signal.Signals) -> None:
        logger.info("%s empfangen - fahre nach dem laufenden Batch herunter", sig.name)
        self.request_stop()

    def request_stop(self) -> None:
        self.state = RunnerState.STOPPING
        self._stop_event.set()
        self._resume_event.set()  # aus einer Pause aufwecken

    def pause(self, reason: str = "") -> None:
        """Kill-Switch: anhalten ohne den Prozess zu beenden."""
        if self.state is RunnerState.PAUSED:
            return
        logger.warning("Konnektor angehalten%s", f": {reason}" if reason else "")
        self.state = RunnerState.PAUSED
        self._resume_event.clear()
        self.metrics.set_up(False)

    def resume(self, reason: str = "") -> None:
        if self.state is not RunnerState.PAUSED:
            return
        logger.info("Konnektor laeuft weiter%s", f": {reason}" if reason else "")
        self.state = RunnerState.RUNNING
        self._resume_event.set()
        self.metrics.set_up(True)

    async def handle_control_message(self, raw: bytes | str) -> None:
        """Verarbeitet eine Nachricht vom Kontroll-Subject.

        Format: {"command": "pause"|"resume"|"stop", "connector_id": "...", "reason": "..."}
        Ohne connector_id gilt der Befehl fuer alle Konnektoren.
        """
        try:
            message = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("Kontrollnachricht ist kein gueltiges JSON, ignoriert")
            return
        target = message.get("connector_id")
        if target not in (None, "", "*", self.settings.connector_id):
            return
        command = str(message.get("command", "")).lower()
        reason = str(message.get("reason", ""))
        if command == "pause":
            self.pause(reason)
        elif command == "resume":
            self.resume(reason)
        elif command == "stop":
            logger.warning("Stop-Befehl empfangen%s", f": {reason}" if reason else "")
            self.request_stop()
        else:
            logger.warning("Unbekannter Kontrollbefehl %r", command)

    async def _subscribe_control(self) -> None:
        if self._control_subscriber is None:
            return
        subject = f"{self.settings.nats.control_subject}.>"
        try:
            await self._control_subscriber(subject, self.handle_control_message)
            logger.info("Kill-Switch aktiv auf %s", subject)
        except Exception as exc:  # noqa: BLE001 - ohne Kill-Switch laeuft es weiter
            logger.warning("Kill-Switch konnte nicht abonniert werden: %s", exc)

    # -- Batchverarbeitung ------------------------------------------------

    async def process_batch(self, result: FetchResult) -> int:
        """Verarbeitet einen Abruf vollstaendig. Gibt die Zahl der
        veroeffentlichten Nachrichten zurueck."""
        async with self._current_batch_lock:
            if not result.records:
                return 0

            # 2. Absicht festhalten, bevor irgendetwas nach draussen geht.
            cursor_value = (
                result.next_cursor
                if result.next_cursor is not None
                else (self.cursors.committed.value if self.cursors.committed else None)
            )
            await self.cursors.begin(cursor_value)

            self.metrics.count("fetched", len(result.records))

            # 3. Bronze. Vor dem Publish, damit die Rohdaten auch dann
            #    vorliegen, wenn die Normalisierung scheitert.
            if self.bronze is not None:
                for record in result.records:
                    await self.bronze.add(record.payload, fetched_at=record.fetched_at)

            # Schema-Drift: meldet, verwirft aber nichts.
            for record in result.records:
                if isinstance(record.payload, dict):
                    report = self.drift.inspect(record.payload)
                    for finding in report.findings:
                        self.metrics.drift(finding.kind.value)
                        self.metrics.error(ErrorKind.SCHEMA_DRIFT.value)

            # 4. Normalisieren.
            messages: list[CanonicalMessage] = []
            for record in result.records:
                try:
                    messages.extend(self.connector.normalize(record))
                except Exception as exc:  # noqa: BLE001
                    # Ein unbrauchbarer Satz darf den Batch nicht kippen: die
                    # Rohdaten liegen in Bronze und sind nachverarbeitbar.
                    self.metrics.error(classify(exc).value)
                    logger.exception("Normalisierung fehlgeschlagen, Satz uebersprungen")
            self.metrics.count("normalized", len(messages))

            if not messages:
                await self.cursors.commit()
                self.metrics.cursor_committed()
                return 0

            # 5. Veroeffentlichen und auf Bestaetigung warten.
            payloads = [
                (
                    f"{self.settings.nats.subject_prefix}.{m.subject_suffix}",
                    m.payload,
                    m.dedupe_key,
                )
                for m in messages
            ]
            with self.metrics.publish_timer():
                publish_result = await self.publisher.publish_batch(payloads)

            self.metrics.count("published", publish_result.published)
            self.metrics.count("skipped_duplicate", publish_result.duplicates)
            self.messages_published += publish_result.published
            self.duplicates_skipped += publish_result.duplicates

            newest = max(
                (m.observed_at for m in messages if m.observed_at is not None),
                default=None,
            )
            if newest is not None:
                self.metrics.observe_lag(newest)

            # 6. Erst jetzt festschreiben.
            await self.cursors.commit()
            self.metrics.cursor_committed()
            self.metrics.mark_success()

            self.batches_completed += 1
            self.records_processed += len(result.records)
            return publish_result.published

    # -- Hauptschleife ----------------------------------------------------

    async def run(self, *, max_batches: int | None = None) -> None:
        """Laeuft, bis gestoppt wird. `max_batches` begrenzt Testlaeufe."""
        self.state = RunnerState.RUNNING
        await self.publisher.connect()
        await self._subscribe_control()
        cursor = await self.cursors.restore()
        if self.cursors.recovered_interrupted:
            self.metrics.error("interrupted_batch_recovered")

        if not self.settings.enabled:
            self.pause("ueber die Konfiguration deaktiviert")
        else:
            self.metrics.set_up(True)

        logger.info(
            "Konnektor %s gestartet (Quelle %s), Wiederaufnahme ab %r",
            self.settings.connector_id, self.settings.source_id,
            cursor.value if cursor else None,
        )

        batches = 0
        try:
            while not self._stop_event.is_set():
                if max_batches is not None and batches >= max_batches:
                    break

                # Kill-Switch: hier wird gewartet, ohne die Quelle anzufassen.
                if not self._resume_event.is_set():
                    await self._wait_for(self._resume_event.wait())
                    if self._stop_event.is_set():
                        break

                try:
                    result = await asyncio.wait_for(
                        self.connector.fetch(
                            self.cursors.committed.value if self.cursors.committed else None
                        ),
                        timeout=self.settings.fetch_timeout_s,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    kind = classify(exc)
                    self.metrics.error(kind.value)
                    self.metrics.set_circuit_state(self.connector.breaker.state.value)
                    logger.error("Abruf fehlgeschlagen (%s): %s", kind.value, exc)
                    await self.cursors.abort()
                    await self._idle(self.settings.poll_interval_s)
                    continue

                batches += 1
                try:
                    await self.process_batch(result)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    kind = classify(exc)
                    self.metrics.error(kind.value)
                    logger.error(
                        "Batch fehlgeschlagen (%s) - Cursor bleibt stehen, "
                        "der Batch wird wiederholt: %s", kind.value, exc,
                    )
                    await self.cursors.abort()
                    await self._idle(self.settings.poll_interval_s)
                    continue

                if result.has_more and not self._stop_event.is_set():
                    continue  # sofort weiter, die Quelle hat noch Daten
                await self._idle(self.settings.poll_interval_s)
        finally:
            await self.shutdown()

    async def _idle(self, seconds: float) -> None:
        """Wartezeit, in der Bronze gepuffert und Spool nachgereicht wird."""
        if self.bronze is not None:
            await self.bronze.maybe_flush()
            self.metrics.set_bronze_buffer(self.bronze.buffered_records)
            if self.bronze.spooled_batches:
                await self.bronze.drain_spool()
        await self._wait_for(asyncio.sleep(seconds))

    async def _wait_for(self, coro: Any) -> None:
        """Wartet, laesst sich aber vom Stop-Signal unterbrechen."""
        stop_task = asyncio.ensure_future(self._stop_event.wait())
        work_task = asyncio.ensure_future(coro)
        try:
            await asyncio.wait({stop_task, work_task}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (stop_task, work_task):
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

    async def shutdown(self) -> None:
        """Sauberes Herunterfahren.

        Wichtig ist die Reihenfolge: erst den laufenden Batch abwarten (ueber
        das Lock), dann Bronze schreiben, dann Verbindungen schliessen. Ein
        offener Bronze-Puffer waere verlorene Rohdaten.
        """
        if self.state is RunnerState.STOPPED:
            return
        self.state = RunnerState.STOPPING
        logger.info("Fahre herunter ...")

        # Auf einen laufenden Batch warten, statt ihn abzuschneiden.
        async with self._current_batch_lock:
            pass

        if self.bronze is not None:
            try:
                await self.bronze.close()
            except Exception as exc:  # noqa: BLE001
                logger.error("Bronze-Puffer konnte nicht geschrieben werden: %s", exc)
                self.metrics.error(ErrorKind.STORAGE_UNAVAILABLE.value)

        for closer, name in (
            (self.publisher.close, "Bus"),
            (self.connector.close, "HTTP-Client"),
            (self._cursor_store.close, "Cursor-Speicher"),
        ):
            try:
                await closer()
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s konnte nicht sauber geschlossen werden: %s", name, exc)

        self.metrics.set_up(False)
        self.state = RunnerState.STOPPED
        logger.info(
            "Beendet: %d Batches, %d Saetze, %d Nachrichten veroeffentlicht, "
            "%d Duplikate verworfen",
            self.batches_completed, self.records_processed,
            self.messages_published, self.duplicates_skipped,
        )


def build_cursor_store(settings: ConnectorSettings) -> CursorStore:
    """Baut den Cursor-Speicher nach Konfiguration."""
    from argus_connector.cursor import (
        ChainedCursorStore,
        MemoryCursorStore,
        PostgresCursorStore,
        ValkeyCursorStore,
    )

    backend = settings.cursor.backend
    if backend == "memory":
        return MemoryCursorStore()
    if backend == "valkey":
        return ValkeyCursorStore(settings.cursor.valkey_url, key_prefix=settings.cursor.key_prefix)
    if backend == "postgres":
        if not settings.cursor.postgres_dsn:
            raise ConnectorError(
                "cursor.backend=postgres, aber ARGUS_CURSOR__POSTGRES_DSN ist leer",
                kind=ErrorKind.CURSOR_UNAVAILABLE,
            )
        return PostgresCursorStore(
            settings.cursor.postgres_dsn, schema=settings.cursor.postgres_schema
        )
    if not settings.cursor.postgres_dsn:
        raise ConnectorError(
            "cursor.backend=chained braucht ARGUS_CURSOR__POSTGRES_DSN als dauerhafte "
            "Schicht. Ohne sie bedeutet ein geleerter Cache einen Neulauf von vorn.",
            kind=ErrorKind.CURSOR_UNAVAILABLE,
        )
    return ChainedCursorStore(
        ValkeyCursorStore(settings.cursor.valkey_url, key_prefix=settings.cursor.key_prefix),
        PostgresCursorStore(
            settings.cursor.postgres_dsn, schema=settings.cursor.postgres_schema
        ),
    )
