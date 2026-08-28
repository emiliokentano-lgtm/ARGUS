"""Veroeffentlichung auf dem Message Bus.

At-least-once, nicht at-most-once: eine Nachricht darf doppelt ankommen, aber
nie verloren gehen. Umgesetzt ueber zwei Mechanismen, die zusammenwirken:

* Der Konnektor wartet auf die JetStream-Bestaetigung, bevor der Cursor
  festgeschrieben wird (siehe cursor.py). Ohne Bestaetigung gilt die Nachricht
  als nicht zugestellt.
* Jede Nachricht traegt ihren dedupe_key als Nats-Msg-Id. JetStream verwirft
  innerhalb seines Dedupe-Fensters Nachrichten mit gleicher Id. Eine
  Wiederholung nach einem Absturz erzeugt damit keine Dublette im Stream,
  solange sie innerhalb des Fensters passiert - und danach faengt sie der
  dedupe_key in der Datenbank.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from argus_connector.retry import ConnectorError, ErrorKind

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PublishResult:
    published: int
    duplicates: int = 0

    @property
    def total(self) -> int:
        return self.published + self.duplicates


class BusUnavailable(ConnectorError):
    kind = ErrorKind.BUS_UNAVAILABLE


@runtime_checkable
class Publisher(Protocol):
    async def connect(self) -> None: ...
    async def publish(self, subject: str, payload: dict[str, Any], *, dedupe_key: str) -> bool: ...
    async def publish_batch(self, messages: Sequence[tuple[str, dict[str, Any], str]]) -> PublishResult: ...
    async def close(self) -> None: ...


class MemoryPublisher:
    """Publisher fuer Tests.

    Bildet das Dedupe-Verhalten von JetStream nach, damit Tests dieselbe
    Semantik sehen wie der Betrieb: eine bereits gesehene Msg-Id gilt als
    zugestellt, erhoeht aber den Duplikatzaehler.
    """

    def __init__(self, *, fail_after: int | None = None) -> None:
        self.messages: list[tuple[str, dict[str, Any], str]] = []
        self.seen_ids: set[str] = set()
        self.duplicates = 0
        self.connected = False
        self._fail_after = fail_after
        self._published = 0

    async def connect(self) -> None:
        self.connected = True

    async def publish(self, subject: str, payload: dict[str, Any], *, dedupe_key: str) -> bool:
        if self._fail_after is not None and self._published >= self._fail_after:
            raise BusUnavailable("Bus (simuliert) nicht erreichbar")
        self._published += 1
        if dedupe_key in self.seen_ids:
            self.duplicates += 1
            return False
        self.seen_ids.add(dedupe_key)
        self.messages.append((subject, payload, dedupe_key))
        return True

    async def publish_batch(
        self, messages: Sequence[tuple[str, dict[str, Any], str]]
    ) -> PublishResult:
        published = duplicates = 0
        for subject, payload, dedupe_key in messages:
            if await self.publish(subject, payload, dedupe_key=dedupe_key):
                published += 1
            else:
                duplicates += 1
        return PublishResult(published, duplicates)

    async def close(self) -> None:
        self.connected = False


class NatsPublisher:
    """JetStream-Publisher mit Bestaetigung je Nachricht."""

    def __init__(
        self,
        url: str,
        *,
        stream: str = "ARGUS_RAW",
        connect_timeout_s: float = 5.0,
        ack_timeout_s: float = 10.0,
        max_reconnect_attempts: int = -1,
        connection: Any = None,
    ) -> None:
        self._url = url
        self._stream = stream
        self._connect_timeout_s = connect_timeout_s
        self._ack_timeout_s = ack_timeout_s
        self._max_reconnect_attempts = max_reconnect_attempts
        self._nc = connection
        self._js: Any = None
        self.duplicates = 0

    async def connect(self) -> None:
        if self._nc is None:
            import nats  # lokal importiert: optionale Abhaengigkeit

            try:
                self._nc = await nats.connect(
                    self._url,
                    connect_timeout=self._connect_timeout_s,
                    max_reconnect_attempts=self._max_reconnect_attempts,
                    name="argus-connector",
                )
            except Exception as exc:  # noqa: BLE001
                raise BusUnavailable(f"NATS unter {self._url} nicht erreichbar: {exc}") from exc
        self._js = self._nc.jetstream()

    async def publish(self, subject: str, payload: dict[str, Any], *, dedupe_key: str) -> bool:
        if self._js is None:
            await self.connect()
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=str).encode()
        try:
            ack = await self._js.publish(
                subject,
                body,
                timeout=self._ack_timeout_s,
                # Nats-Msg-Id: JetStream verwirft Wiederholungen innerhalb des
                # Dedupe-Fensters des Streams.
                headers={"Nats-Msg-Id": dedupe_key},
                stream=self._stream,
            )
        except Exception as exc:  # noqa: BLE001
            raise BusUnavailable(f"Veroeffentlichung auf {subject} fehlgeschlagen: {exc}") from exc
        if getattr(ack, "duplicate", False):
            self.duplicates += 1
            return False
        return True

    async def publish_batch(
        self, messages: Sequence[tuple[str, dict[str, Any], str]]
    ) -> PublishResult:
        published = duplicates = 0
        for subject, payload, dedupe_key in messages:
            if await self.publish(subject, payload, dedupe_key=dedupe_key):
                published += 1
            else:
                duplicates += 1
        return PublishResult(published, duplicates)

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.drain()
            self._nc = None
            self._js = None
