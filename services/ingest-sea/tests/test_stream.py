"""Verbindungsmanagement: Abbruch, Wiederaufbau, Abweisung, Rueckstau."""

from __future__ import annotations

import asyncio
import time

import pytest
from aisstream.stream import AisStreamClient, FatalStreamError

# Flacher Import statt eines relativen: unter services/ gibt es mehrere
# Verzeichnisse namens 'tests' ohne __init__.py, und pytest legt sie auf
# denselben Modulnamen. Der Dateiname traegt deshalb das Paket im Namen.
from aisstream_fakes import (
    CONNECTION_CLOSED_CLEANLY,
    CONNECTION_LOST,
    FakeServer,
    position_message,
)
from websockets.exceptions import InvalidStatus

WHEN = "2026-08-28 09:14:03.221 +0000 UTC"

pytestmark = pytest.mark.asyncio


async def _drain(client: AisStreamClient, count: int, timeout_s: float = 5.0) -> list[dict]:
    """Wartet, bis `count` Nachrichten durch sind - oder bricht ab."""
    collected: list[dict] = []
    deadline = time.monotonic() + timeout_s
    while len(collected) < count and time.monotonic() < deadline:
        collected.extend(await client.batch(max_size=count, max_wait_s=0.05))
    return collected


async def test_subscription_is_sent_on_connect(ais_settings) -> None:
    server = FakeServer([position_message(211331640, 53.5, 8.1, WHEN)])
    client = AisStreamClient(ais_settings, connect=server)
    client.start()
    try:
        assert len(await _drain(client, 1)) == 1
        subscription = server.connections[0].subscriptions[0]
        assert subscription["APIKey"] == "test-key"
        assert subscription["BoundingBoxes"] == [[[53.0, 6.0], [55.0, 9.0]]]
        assert "PositionReport" in subscription["FilterMessageTypes"]
    finally:
        await client.stop()


async def test_subscription_is_rebuilt_after_every_reconnect(ais_settings) -> None:
    """Der Fehler, der am teuersten ist, weil er wie 'ruhige See' aussieht.

    AISStream haelt kein Abonnement ueber einen Abbruch hinweg. Wer es nach
    der Wiederverbindung nicht erneut sendet, bekommt eine stehende Leitung,
    ueber die nie wieder etwas kommt - und keinen einzigen Fehler.
    """
    server = FakeServer(
        [position_message(211331640, 53.5, 8.1, WHEN), CONNECTION_LOST()],
        [position_message(211331641, 53.6, 8.2, WHEN)],
    )
    client = AisStreamClient(ais_settings, connect=server)
    client.start()
    try:
        assert len(await _drain(client, 2)) == 2
        assert len(server.connections) == 2
        for connection in server.connections:
            assert len(connection.subscriptions) == 1
            assert connection.subscriptions[0]["APIKey"] == "test-key"
    finally:
        await client.stop()


async def test_abort_without_close_frame_recovers(ais_settings) -> None:
    """Abbruch ohne Close-Frame: beide Frames sind None."""
    server = FakeServer(
        [position_message(211331640, 53.5, 8.1, WHEN), CONNECTION_LOST()],
        [position_message(211331641, 53.6, 8.2, WHEN)],
    )
    client = AisStreamClient(ais_settings, connect=server)
    client.start()
    try:
        messages = await _drain(client, 2)
        assert len(messages) == 2
        assert client.successful_connections == 2
    finally:
        await client.stop()


async def test_clean_close_also_reconnects(ais_settings) -> None:
    """Auch ein geordneter Schluss ist kein Grund, stehenzubleiben."""
    server = FakeServer(
        [position_message(211331640, 53.5, 8.1, WHEN), CONNECTION_CLOSED_CLEANLY()],
        [position_message(211331641, 53.6, 8.2, WHEN)],
    )
    client = AisStreamClient(ais_settings, connect=server)
    client.start()
    try:
        assert len(await _drain(client, 2)) == 2
    finally:
        await client.stop()


async def test_silence_on_a_standing_line_counts_as_dead(ais_settings) -> None:
    ais_settings = ais_settings.model_copy(update={"idle_timeout_s": 0.15})
    server = FakeServer(
        [],  # Leitung steht, es kommt nie etwas
        [position_message(211331640, 53.5, 8.1, WHEN)],
    )
    client = AisStreamClient(ais_settings, connect=server)
    client.start()
    try:
        assert len(await _drain(client, 1, timeout_s=5.0)) == 1
        assert len(server.connections) == 2
    finally:
        await client.stop()


async def test_recovery_stays_well_under_thirty_seconds(ais_settings) -> None:
    """Akzeptanzkriterium: Wiederherstellung in unter 30 s.

    Gemessen mit dem konfigurierten Deckel, nicht mit dem Testdeckel - sonst
    misst der Test seine eigenen Einstellungen.
    """
    ais_settings = ais_settings.model_copy(
        update={"reconnect_base_delay_s": 0.5, "reconnect_max_delay_s": 30.0}
    )
    server = FakeServer(
        [position_message(211331640, 53.5, 8.1, WHEN), CONNECTION_LOST()],
        [position_message(211331641, 53.6, 8.2, WHEN)],
    )
    client = AisStreamClient(ais_settings, connect=server)
    client.start()
    try:
        await _drain(client, 1)
        started = time.monotonic()
        assert len(await _drain(client, 1, timeout_s=30.0)) == 1
        elapsed = time.monotonic() - started
        assert elapsed < 30.0, f"Wiederherstellung dauerte {elapsed:.1f} s"
    finally:
        await client.stop()


async def test_backoff_grows_and_is_capped(ais_settings) -> None:
    ais_settings = ais_settings.model_copy(
        update={"reconnect_base_delay_s": 1.0, "reconnect_max_delay_s": 8.0}
    )
    client = AisStreamClient(ais_settings, connect=FakeServer())
    ceilings = [min(8.0, 1.0 * 2 ** (attempt - 1)) for attempt in range(1, 8)]
    for attempt, ceiling in enumerate(ceilings, start=1):
        # Voller Jitter: der Wert liegt zwischen 0 und der Obergrenze.
        samples = [client._backoff(attempt) for _ in range(50)]
        assert all(0.0 <= sample <= ceiling for sample in samples)
    assert ceilings[-1] == 8.0


async def test_invalid_api_key_stops_instead_of_hammering(ais_settings) -> None:
    """Ein falscher Schluessel wird durch Wiederholen nicht richtig.

    Ein Konnektor, der sich im Sekundentakt mit falschem Schluessel wieder
    anmeldet, wird zu Recht gesperrt - Kapitel 14.
    """
    server = FakeServer([{"error": "Invalid API key"}])
    client = AisStreamClient(ais_settings, connect=server)
    client.start()
    await asyncio.sleep(0.3)
    try:
        assert isinstance(client.fatal, FatalStreamError)
        assert not client.running
        assert server.attempts == 1
        with pytest.raises(FatalStreamError):
            await client.batch(max_size=10, max_wait_s=0.01)
    finally:
        await client.stop()


async def test_http_401_at_handshake_is_fatal(ais_settings) -> None:
    class _Response:
        status_code = 401

    server = FakeServer()
    server.raise_on_connect = InvalidStatus(_Response())
    client = AisStreamClient(ais_settings, connect=server)
    client.start()
    await asyncio.sleep(0.3)
    try:
        assert isinstance(client.fatal, FatalStreamError)
        assert "401" in str(client.fatal)
        assert server.attempts == 1
    finally:
        await client.stop()


async def test_non_fatal_service_error_is_logged_and_survived(ais_settings) -> None:
    """Nicht jede Fehlermeldung des Dienstes ist ein Grund aufzuhoeren."""
    server = FakeServer(
        [
            {"error": "Bounding box too large, truncated"},
            position_message(211331640, 53.5, 8.1, WHEN),
        ]
    )
    client = AisStreamClient(ais_settings, connect=server)
    client.start()
    try:
        assert len(await _drain(client, 1)) == 1
        assert client.fatal is None
    finally:
        await client.stop()


async def test_non_json_message_is_skipped(ais_settings) -> None:
    server = FakeServer(["<html>502 Bad Gateway</html>", position_message(211331640, 1, 1, WHEN)])
    client = AisStreamClient(ais_settings, connect=server)
    client.start()
    try:
        assert len(await _drain(client, 1)) == 1
        assert client.messages_received == 1
    finally:
        await client.stop()


async def test_backpressure_drops_oldest_and_counts_it(ais_settings) -> None:
    """Rueckstau ist Datenverlust und wird als solcher gezaehlt.

    Die Alternative - den Leser blockieren zu lassen - verlagert den Rueckstau
    nur in die Puffer darunter. Aus sichtbarem Verlust wuerde ein
    unsichtbares Speicherleck.
    """
    dropped: list[int] = []
    ais_settings = ais_settings.model_copy(update={"queue_size": 5})
    client = AisStreamClient(ais_settings, connect=FakeServer(), on_drop=dropped.append)
    for index in range(12):
        client._offer(position_message(200000000 + index, 53.5, 8.1, WHEN))

    assert client.pending == 5
    assert client.messages_dropped == 7
    assert sum(dropped) == 7
    # Die juengsten sind da, die aeltesten weg.
    batch = await client.batch(max_size=10, max_wait_s=0.01)
    mmsis = [m["MetaData"]["MMSI"] for m in batch]
    assert mmsis == [200000007, 200000008, 200000009, 200000010, 200000011]


async def test_batch_returns_empty_instead_of_blocking(ais_settings) -> None:
    client = AisStreamClient(ais_settings, connect=FakeServer())
    started = time.monotonic()
    assert await client.batch(max_size=10, max_wait_s=0.05) == []
    assert time.monotonic() - started < 1.0


async def test_batch_size_is_respected(ais_settings) -> None:
    client = AisStreamClient(ais_settings, connect=FakeServer())
    for index in range(50):
        client._offer(position_message(200000000 + index, 53.5, 8.1, WHEN))
    batch = await client.batch(max_size=20, max_wait_s=0.01)
    assert len(batch) == 20
    assert client.pending == 30


async def test_stop_is_idempotent_and_leaves_no_task(ais_settings) -> None:
    client = AisStreamClient(ais_settings, connect=FakeServer([]))
    client.start()
    await asyncio.sleep(0.05)
    await client.stop()
    await client.stop()
    assert not client.running
