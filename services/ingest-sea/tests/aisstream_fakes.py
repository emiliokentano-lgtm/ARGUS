"""Ein WebSocket-Doppel, das sich wie die Leitung benimmt - nicht wie ein Mock.

Der Unterschied ist wichtig: ein Mock, der `recv()` mit einer vorbereiteten
Liste beantwortet, testet nicht, was hier zu testen ist. Getestet werden soll
das Verhalten bei einem Abbruch OHNE Close-Frame, bei einem Abbruch mit
Close-Frame, bei Stille auf einer stehenden Leitung und bei einer Abweisung
durch den Dienst. Dafuer muss das Doppel diese Zustaende tatsaechlich
herstellen koennen.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from typing import Any

from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from websockets.frames import Close


def _closed_error() -> ConnectionClosedError:
    """Abbruch ohne Close-Frame: genau der Fehlerfall der Aufgabenstellung.

    websockets unterscheidet ihn von einem geordneten Schluss dadurch, dass
    beide Close-Frames None sind.
    """
    return ConnectionClosedError(None, None)


def _closed_ok() -> ConnectionClosedOK:
    frame = Close(1000, "")
    # rcvd_then_sent ist Pflicht, sobald beide Frames gesetzt sind.
    return ConnectionClosedOK(frame, frame, True)


class FakeConnection:
    """Eine Verbindung mit einem Skript."""

    def __init__(self, script: Iterable[Any]) -> None:
        # Elemente: dict -> als JSON senden; str -> woertlich senden;
        # Exception -> werfen; float -> so lange schweigen; callable -> erst
        # beim Senden auswerten (fuer Nachrichten, die 'jetzt' tragen sollen).
        self._script = list(script)
        self.sent: list[str] = []
        self.closed = False

    async def send(self, payload: str) -> None:
        if self.closed:
            raise _closed_error()
        self.sent.append(payload)

    async def recv(self) -> str:
        if self.closed:
            raise _closed_error()
        if not self._script:
            # Skript zu Ende: Leitung steht, es kommt nichts mehr. Der
            # Leerlauf-Zeitgeber muss das aufloesen.
            await asyncio.sleep(3600)
        item = self._script.pop(0)
        if callable(item):
            item = item()
        if isinstance(item, BaseException):
            self.closed = True
            raise item
        if isinstance(item, int | float):
            await asyncio.sleep(float(item))
            return await self.recv()
        return item if isinstance(item, str) else json.dumps(item)

    async def close(self) -> None:
        self.closed = True

    @property
    def subscriptions(self) -> list[dict[str, Any]]:
        return [json.loads(payload) for payload in self.sent]


class FakeServer:
    """Liefert je Verbindungsversuch eine neue FakeConnection."""

    def __init__(self, *sessions: Iterable[Any]) -> None:
        self._sessions = [list(session) for session in sessions]
        self.connections: list[FakeConnection] = []
        self.attempts = 0
        # Wird bei jedem Versuch geworfen, statt eine Verbindung zu liefern.
        self.raise_on_connect: BaseException | None = None

    async def __call__(self, url: str, **kwargs: Any) -> FakeConnection:
        self.attempts += 1
        if self.raise_on_connect is not None:
            raise self.raise_on_connect
        script = self._sessions.pop(0) if self._sessions else []
        connection = FakeConnection(script)
        self.connections.append(connection)
        return connection


def live_position(mmsi: int, lat: float = 53.5, lon: float = 8.1):
    """Eine Nachricht, deren Zeitstempel erst beim Senden entsteht.

    Damit laesst sich ein Live-Feed nachbilden: die Quelle meldet, ARGUS
    empfaengt Millisekunden spaeter. Nur so misst ingest_lag_seconds das, was
    der Konnektor beitraegt, statt das Alter der Fixtures.
    """
    from datetime import UTC, datetime

    def make() -> dict[str, Any]:
        now = datetime.now(UTC)
        stamp = (
            now.strftime("%Y-%m-%d %H:%M:%S.") + f"{now.microsecond // 10000:02d}" + " +0000 UTC"
        )
        return position_message(mmsi, lat, lon, stamp)

    return make


def position_message(mmsi: int, lat: float, lon: float, when: str) -> dict[str, Any]:
    return {
        "MessageType": "PositionReport",
        "MetaData": {
            "MMSI": mmsi,
            "MMSI_String": mmsi,
            "ShipName": "TESTSCHIFF",
            "latitude": lat,
            "longitude": lon,
            "time_utc": when,
        },
        "Message": {
            "PositionReport": {
                "MessageID": 1,
                "RepeatIndicator": 0,
                "UserID": mmsi,
                "Valid": True,
                "NavigationalStatus": 0,
                "RateOfTurn": 0,
                "Sog": 10.5,
                "PositionAccuracy": True,
                "Longitude": lon,
                "Latitude": lat,
                "Cog": 90.0,
                "TrueHeading": 90,
                "Timestamp": 10,
                "SpecialManoeuvreIndicator": 0,
                "Spare": 0,
                "Raim": False,
                "CommunicationState": 2148,
            }
        },
    }


CONNECTION_LOST = _closed_error
CONNECTION_CLOSED_CLEANLY = _closed_ok
