"""Durchsatz und Dauerlauf.

ZUM AKZEPTANZKRITERIUM "2.000 NACHRICHTEN/S OHNE RUECKSTAU"
-----------------------------------------------------------
Gemessen wird der Weg, den der Konnektor verantwortet: Warteschlange ->
Parser -> Normalisierung -> kanonische Nachricht. Was danach kommt - die
JetStream-Bestaetigung - haengt am Netz und am Broker und ist keine Eigenschaft
dieses Codes; sie wird mit dem MemoryPublisher ersetzt, der dasselbe
Dedupe-Verhalten hat.

Was das Kriterium damit belegt und was nicht: es belegt, dass der Konnektor
2.000 Nachrichten/s uebersetzen kann, ohne dass die Warteschlange waechst. Es
belegt NICHT, dass eine bestimmte NATS-Installation sie annimmt. Der zweite
Teil ist eine Aussage ueber den Betrieb und gehoert in eine Lastprobe gegen
den echten Stack.

ZUM AKZEPTANZKRITERIUM "24 H OHNE SPEICHERWACHSTUM"
---------------------------------------------------
24 Stunden laufen hier nicht. Was hier laeuft, ist der Mechanismus, der in 24
Stunden Speicher fressen wuerde: die Positionshistorie je MMSI, die Menge der
gesehenen unbekannten Typen und die Warteschlange. Alle drei sind hart
begrenzt, und der Test weist das mit einer Nachrichtenzahl nach, die die
Grenzen um ein Vielfaches ueberschreitet. Ein echter 24-Stunden-Lauf gehoert
in die Betriebsabnahme, nicht in die Testsuite.
"""

from __future__ import annotations

import gc
import sys
import time
import tracemalloc

import pytest
from aisstream.normalize import Normalizer
from aisstream.parser import UnsupportedMessageTypeError, parse
from aisstream_fakes import FakeServer

from argus_connector import MemoryPublisher

# Zielwert der Aufgabenstellung.
TARGET_MESSAGES_PER_SECOND = 2_000

# Unter einem Tracer misst ein Durchsatztest den Tracer. coverage.py bremst
# Python um den Faktor zwei bis vier - eine Zahl, die darunter entsteht, ist
# keine Aussage ueber den Konnektor. Die Messung gehoert in einen Lauf ohne
# Instrumentierung; ein still herabgesetzter Grenzwert waere schlimmer als
# ein uebersprungener Test, weil er weiter gruen aussaehe.
_TRACED = sys.gettrace() is not None
needs_clean_timing = pytest.mark.skipif(
    _TRACED,
    reason="Durchsatzmessung nur ohne Tracer aussagekraeftig (z. B. ohne --cov)",
)

pytestmark = pytest.mark.asyncio


def _expand(stream_messages: list[dict], count: int) -> list[dict]:
    """Vervielfacht die Fixtures auf `count` Nachrichten.

    Mit veraenderter MMSI je Runde: sonst trifft jede Wiederholung dieselben
    Eintraege in der Positionshistorie, und der teuerste Zweig - eine neue
    MMSI anlegen und die aelteste verdraengen - liefe nie.
    """
    expanded: list[dict] = []
    round_index = 0
    while len(expanded) < count:
        for message in stream_messages:
            if len(expanded) >= count:
                break
            copy = {
                "MessageType": message["MessageType"],
                "MetaData": dict(message["MetaData"]),
                "Message": {key: dict(value) for key, value in message["Message"].items()},
            }
            body = next(iter(copy["Message"].values()))
            if "UserID" in body:
                body["UserID"] = body["UserID"] + round_index * 1000
                copy["MetaData"]["MMSI"] = body["UserID"]
            expanded.append(copy)
        round_index += 1
    return expanded


@needs_clean_timing
async def test_parse_and_normalize_reach_the_target(stream_messages) -> None:
    """Der eigentliche Durchsatztest: Uebersetzung, gemessen an der Uhr."""
    messages = _expand(stream_messages, 20_000)
    normalizer = Normalizer(collector="ingest-sea-aisstream@0.1.0")
    now = time.time()

    started = time.perf_counter()
    produced = 0
    for message in messages:
        try:
            parsed = parse(message)
        except UnsupportedMessageTypeError:
            continue
        if normalizer.to_observation(parsed, now=now) is not None:
            produced += 1
        if normalizer.to_entity(parsed, now=now) is not None:
            produced += 1
    elapsed = time.perf_counter() - started

    rate = len(messages) / elapsed
    print(
        f"\nDurchsatz Uebersetzung: {rate:,.0f} Nachrichten/s "
        f"({len(messages):,} in {elapsed:.2f} s, {produced:,} kanonische Nachrichten)"
    )
    assert rate >= TARGET_MESSAGES_PER_SECOND, (
        f"{rate:,.0f} Nachrichten/s liegen unter dem Ziel von {TARGET_MESSAGES_PER_SECOND:,}/s"
    )


@needs_clean_timing
async def test_full_chain_reaches_the_target(settings, ais_settings, stream_messages) -> None:
    """Dieselbe Messung durch den vollstaendigen Runner.

    Hier kommen Warteschlange, Stapelbildung, Bronze-freie Verarbeitung,
    Veroeffentlichung, Cursor-Festschreibung und Metriken hinzu. Der Wert ist
    niedriger als oben - das ist der Preis der Betriebseigenschaften, und
    genau deshalb wird er gemessen und nicht geschaetzt.
    """
    from aisstream.connector import AisStreamConnector
    from aisstream.stream import AisStreamClient

    count = 12_000
    messages = _expand(stream_messages, count)
    ais_settings = ais_settings.model_copy(
        update={"queue_size": count + 1_000, "max_batch_size": 2_000}
    )
    connector = AisStreamConnector(
        settings,
        ais_settings,
        client=AisStreamClient(ais_settings, connect=FakeServer(messages)),
    )
    publisher = MemoryPublisher()

    from test_connector import _run

    started = time.perf_counter()
    runner = await _run(connector, settings, publisher, expect=count, timeout_s=120.0)
    elapsed = time.perf_counter() - started

    # Gezaehlt werden die Rohnachrichten, die durch die Kette gegangen sind.
    # records_processed und messages_published unterscheiden sich: Typ 19
    # erzeugt zwei kanonische Nachrichten, nicht unterstuetzte Typen keine.
    processed = runner.records_processed
    rate = processed / elapsed
    print(
        f"\nDurchsatz Gesamtkette: {rate:,.0f} Nachrichten/s "
        f"({processed:,} in {elapsed:.2f} s, "
        f"{runner.messages_published:,} veroeffentlicht)"
    )
    assert runner.messages_published >= count
    assert rate >= TARGET_MESSAGES_PER_SECOND, (
        f"{rate:,.0f} Nachrichten/s liegen unter dem Ziel von {TARGET_MESSAGES_PER_SECOND:,}/s"
    )


@needs_clean_timing
async def test_queue_does_not_grow_at_target_rate(settings, ais_settings, stream_messages) -> None:
    """Kein Rueckstau: die Warteschlange ist am Ende leer.

    'Ohne Rueckstau' heisst nicht 'schnell', sondern: der Zulauf wird
    abgetragen. Ein Konnektor, der 2.000/s uebersetzt und 2.100/s bekommt,
    erfuellt das Kriterium nicht - er verliert nur langsam.
    """
    from aisstream.connector import AisStreamConnector
    from aisstream.stream import AisStreamClient

    count = 8_000
    messages = _expand(stream_messages, count)
    ais_settings = ais_settings.model_copy(update={"queue_size": count + 1_000})
    client = AisStreamClient(ais_settings, connect=FakeServer(messages))
    connector = AisStreamConnector(settings, ais_settings, client=client)

    from test_connector import _run

    # Laufen lassen, bis die Warteschlange tatsaechlich leer ist - nicht bis
    # eine Zahl erreicht ist. Genau das ist die Frage: wird der Zulauf
    # abgetragen?
    await _run(
        connector,
        settings,
        MemoryPublisher(),
        until=lambda r: client.pending == 0 and r.messages_published >= count,
        timeout_s=120.0,
    )
    assert client.pending == 0
    assert client.messages_dropped == 0


async def test_bounded_state_over_a_long_run(stream_messages) -> None:
    """Der 24-Stunden-Teil: waechst irgendetwas mit der Nachrichtenzahl?

    Gemessen wird der Speicher, den der Normalizer haelt, nachdem er ein
    Vielfaches seiner Grenzen gesehen hat. Waechst er weiter, waechst er auch
    nach 24 Stunden - und dann faellt der Prozess irgendwann um.
    """
    history_size = 500
    normalizer = Normalizer(collector="test@1", position_history_size=history_size)
    messages = _expand(stream_messages, 40_000)
    now = time.time()

    gc.collect()
    tracemalloc.start()
    baseline = tracemalloc.take_snapshot()

    for index, message in enumerate(messages):
        try:
            parsed = parse(message)
        except UnsupportedMessageTypeError:
            continue
        normalizer.to_observation(parsed, now=now)
        normalizer.to_entity(parsed, now=now)
        if index == 20_000:
            gc.collect()
            midpoint = tracemalloc.take_snapshot()

    gc.collect()
    final = tracemalloc.take_snapshot()
    tracemalloc.stop()

    grew_first = sum(s.size_diff for s in midpoint.compare_to(baseline, "filename"))
    grew_second = sum(s.size_diff for s in final.compare_to(midpoint, "filename"))
    print(
        f"\nSpeicher nach 20.000 Nachrichten: {grew_first / 1024:+.0f} KiB, "
        f"nach weiteren 20.000: {grew_second / 1024:+.0f} KiB"
    )

    # Die Historie ist hart gedeckelt - das ist die eigentliche Zusage.
    assert len(normalizer._last_position) <= history_size
    # Und die zweite Haelfte darf nicht mehr wachsen als die erste: alles,
    # was linear mitwaechst, faellt hier auf.
    assert grew_second <= max(grew_first, 0) + 256 * 1024, (
        f"Speicher waechst weiter: erste Haelfte {grew_first / 1024:+.0f} KiB, "
        f"zweite {grew_second / 1024:+.0f} KiB"
    )


async def test_unknown_types_are_logged_once_not_per_message(settings, ais_settings) -> None:
    """Bei 2.000 Nachrichten/s flutet ein unbekannter Typ sonst das Protokoll.

    Und ein geflutetes Protokoll ist kein Schoenheitsfehler: es verdeckt die
    Fehler, wegen denen man hineinsieht.
    """
    from aisstream.connector import AisStreamConnector
    from aisstream.stream import AisStreamClient

    unknown = {
        "MessageType": "BaseStationReport",
        "MetaData": {"MMSI": 2111234, "time_utc": "2026-08-28 09:00:00.0 +0000 UTC"},
        "Message": {"BaseStationReport": {"MessageID": 4, "UserID": 2111234}},
    }
    connector = AisStreamConnector(
        settings,
        ais_settings,
        client=AisStreamClient(ais_settings, connect=FakeServer([])),
    )
    from argus_connector import RawRecord

    for _ in range(1_000):
        assert connector.normalize(RawRecord(payload=unknown)) == []
    assert connector._unsupported_seen == {"BaseStationReport"}
    await connector.close()


async def test_position_history_stays_bounded_under_many_mmsi(stream_messages) -> None:
    """Zehntausende MMSI in einem Lauf - die Landkarte darf nicht mitwachsen."""
    # Die Grenze liegt bewusst deutlich unter der Zahl verschiedener MMSI im
    # Lauf - sonst wird sie nie erreicht und der Test prueft nichts.
    limit = 200
    normalizer = Normalizer(collector="test@1", position_history_size=limit)
    seen: set[int] = set()
    for message in _expand(stream_messages, 30_000):
        try:
            parsed = parse(message)
        except UnsupportedMessageTypeError:
            continue
        if parsed.position is not None and parsed.position.has_position:
            seen.add(parsed.mmsi)
        normalizer.to_observation(parsed, now=time.time())
    assert len(seen) > limit * 3, "Zu wenige verschiedene MMSI - die Grenze greift nicht"
    assert len(normalizer._last_position) == limit
    assert sys.getsizeof(normalizer._last_position) < 100_000
