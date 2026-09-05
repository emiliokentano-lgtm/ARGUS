"""Der Konnektor im Zusammenspiel mit dem SDK-Runner.

Hier laeuft die vollstaendige Kette: WebSocket-Doppel -> Warteschlange ->
fetch -> Bronze -> normalize -> publish -> Cursor. Was die Einzeltests
zusichern, muss auch dann noch gelten, wenn es durch den Runner geht.
"""

from __future__ import annotations

import asyncio

import pytest
from aisstream.config import POSITION_SUBJECT, STATIC_SUBJECT
from aisstream.connector import AisStreamConnector
from aisstream.stream import AisStreamClient, FatalStreamError
from aisstream_fakes import CONNECTION_LOST, FakeServer, live_position, position_message

from argus_connector import ConnectorRunner, MemoryCursorStore, MemoryPublisher

WHEN = "2026-08-28 09:14:03.221 +0000 UTC"

pytestmark = pytest.mark.asyncio


def _connector(settings, ais_settings, server) -> AisStreamConnector:
    return AisStreamConnector(
        settings, ais_settings, client=AisStreamClient(ais_settings, connect=server)
    )


async def _run(
    connector,
    settings,
    publisher,
    *,
    expect: int = 0,
    until=None,
    store: MemoryCursorStore | None = None,
    timeout_s: float = 15.0,
) -> ConnectorRunner:
    """Laesst den Runner laufen, bis `expect` Nachrichten durch sind.

    Nicht ueber `max_batches`: ein Stromkonnektor entnimmt, was gerade in der
    Warteschlange liegt, und wie viele Stapel dafuer noetig sind, haengt davon
    ab, wie oft der Leser zwischendurch drankam. Ein Test, der Stapel zaehlt,
    misst die Ablaufplanung des Ereignis-Loops - und ist genau deshalb
    unzuverlaessig. Gezaehlt wird, was hinten herauskommt.
    """
    runner = ConnectorRunner(
        connector,
        settings=settings,
        cursor_store=store or MemoryCursorStore(),
        publisher=publisher,
    )
    done = until or (lambda r: r.messages_published + r.duplicates_skipped >= expect)
    task = asyncio.create_task(runner.run())
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if done(runner):
            break
        await asyncio.sleep(0.01)
    runner.request_stop()
    await asyncio.wait_for(task, timeout=5.0)
    return runner


# --- Subjects --------------------------------------------------------------


async def test_positions_and_static_data_go_to_separate_subjects(
    settings, ais_settings, stream_messages
) -> None:
    """Der Constraint aus der Aufgabenstellung, an der Leitung geprueft."""
    sample = [
        m for m in stream_messages if m["MessageType"] in ("PositionReport", "ShipStaticData")
    ][:40]
    server = FakeServer(sample)
    connector = _connector(settings, ais_settings, server)
    publisher = MemoryPublisher()
    await _run(connector, settings, publisher, expect=len(sample))

    subjects = {subject for subject, _, _ in publisher.messages}
    assert subjects <= {POSITION_SUBJECT, STATIC_SUBJECT}
    assert POSITION_SUBJECT in subjects
    assert STATIC_SUBJECT in subjects

    for subject, payload, _ in publisher.messages:
        if subject == POSITION_SUBJECT:
            assert "obs_id" in payload
        else:
            assert "entity_id" in payload


async def test_wrong_subject_prefix_fails_at_construction(settings, ais_settings) -> None:
    broken = settings.model_copy(
        update={"nats": settings.nats.model_copy(update={"subject_prefix": "argus.raw"})}
    )
    with pytest.raises(ValueError, match=r"argus\.canon"):
        AisStreamConnector(broken, ais_settings)


# --- Fehlerfaelle in der Kette --------------------------------------------


async def test_unsupported_types_are_counted_not_fatal(
    settings, ais_settings, stream_messages
) -> None:
    unsupported = [
        m
        for m in stream_messages
        if m["MessageType"] not in ("PositionReport", "ShipStaticData")
        and m["MessageType"]
        not in (
            "StandardClassBPositionReport",
            "ExtendedClassBPositionReport",
            "AidsToNavigationReport",
            "StaticDataReport",
        )
    ]
    assert unsupported, "Ohne nicht unterstuetzte Fixtures testet das hier nichts"
    server = FakeServer([*unsupported, position_message(211331640, 53.5, 8.1, WHEN)])
    connector = _connector(settings, ais_settings, server)
    publisher = MemoryPublisher()
    await _run(connector, settings, publisher, expect=1)

    assert len(publisher.messages) >= 1
    assert connector._unsupported_seen


async def test_a_broken_record_does_not_kill_the_batch(settings, ais_settings) -> None:
    """Ein unbrauchbarer Satz darf die 1.999 anderen nicht mitnehmen.

    Die Rohdaten liegen in Bronze; der Satz ist nachverarbeitbar. Den Stapel
    zu verwerfen waere teurer als ihn zu ueberspringen.
    """
    server = FakeServer(
        [
            {"MessageType": "PositionReport", "MetaData": {}, "Message": {}},
            position_message(211331640, 53.5, 8.1, WHEN),
            position_message(211331641, 53.6, 8.2, WHEN),
        ]
    )
    connector = _connector(settings, ais_settings, server)
    publisher = MemoryPublisher()
    await _run(connector, settings, publisher, expect=2)
    assert len(publisher.messages) == 2


async def test_duplicates_after_reconnect_are_recognised(settings, ais_settings) -> None:
    """Nach einem Abbruch schickt die Quelle Bekanntes erneut.

    Der dedupe_key faengt das ab - er entsteht aus dem Inhalt, nicht aus dem
    Empfangszeitpunkt. Dieselbe Nachricht zweimal ergibt denselben Schluessel.
    """
    duplicated = position_message(211331640, 53.5, 8.1, WHEN)
    server = FakeServer(
        [duplicated, CONNECTION_LOST()],
        [duplicated, position_message(211331641, 53.6, 8.2, WHEN)],
    )
    connector = _connector(settings, ais_settings, server)
    publisher = MemoryPublisher()
    runner = await _run(connector, settings, publisher, expect=3)

    assert publisher.duplicates >= 1
    assert runner.duplicates_skipped >= 1
    # Die Dublette wurde erkannt, die neue Nachricht kam durch.
    assert len({payload["obs_id"] for _, payload, _ in publisher.messages}) == 2


async def test_fatal_error_stops_the_run(settings, ais_settings) -> None:
    server = FakeServer([{"error": "Invalid API key"}])
    connector = _connector(settings, ais_settings, server)
    connector.stream.start()
    await asyncio.sleep(0.2)
    with pytest.raises(FatalStreamError):
        await connector.fetch(None)
    await connector.close()


# --- Gesundheit ------------------------------------------------------------


async def test_health_distinguishes_the_failure_modes(settings, ais_settings) -> None:
    connector = _connector(settings, ais_settings, FakeServer([]))

    not_started = await connector.health()
    assert not not_started.healthy
    assert "laeuft nicht" in not_started.detail

    connector.stream.start()
    await asyncio.sleep(0.1)
    connected = await connector.health()
    assert connected.healthy

    await connector.close()


async def test_health_reports_a_fatal_rejection(settings, ais_settings) -> None:
    connector = _connector(settings, ais_settings, FakeServer([{"error": "unauthorized"}]))
    connector.stream.start()
    await asyncio.sleep(0.2)
    status = await connector.health()
    assert not status.healthy
    assert "dauerhaft abgewiesen" in status.detail
    await connector.close()


# --- Metriken --------------------------------------------------------------


def _metric(connector, name: str, **labels: str) -> float:
    value = connector.metrics.registry.get_sample_value(
        name, {"connector": connector.settings.connector_id, "source": "aisstream", **labels}
    )
    return 0.0 if value is None else value


async def test_ingest_lag_histogram_is_filled(settings, ais_settings, stream_messages) -> None:
    """Die Pflichtmetrik der Aufgabenstellung, mit Beobachtungen darin."""
    sample = [m for m in stream_messages if m["MessageType"] == "PositionReport"][:30]
    connector = _connector(settings, ais_settings, FakeServer(sample))
    await _run(connector, settings, MemoryPublisher(), expect=30)
    assert _metric(connector, "ingest_lag_seconds_count") >= 30


async def test_ingest_lag_p95_is_under_ten_seconds(settings, ais_settings) -> None:
    """Akzeptanzkriterium: p95 von ingest_lag_seconds unter 10 s.

    Gemessen ueber die Histogramm-Buckets, so wie Prometheus es spaeter auch
    rechnet.

    Der Aufbau ist ein nachgebildeter Live-Feed: jede Nachricht bekommt ihren
    Zeitstempel erst in dem Moment, in dem sie ueber die Leitung geht. Damit
    misst das Histogramm genau die Zeit, die der Konnektor braucht - von der
    Meldung bis zur bestaetigten Veroeffentlichung.

    Was es NICHT misst, und das gehoert dazugesagt: die Laufzeit zwischen
    Sender und AISStream. Die ist ohne echten Feed nicht messbar, geht in der
    Produktion aber in dieselbe Kennzahl ein. Das p95 hier ist deshalb eine
    Untergrenze, keine Betriebsmessung.
    """
    count = 400
    server = FakeServer([live_position(200000000 + index) for index in range(count)])
    connector = _connector(settings, ais_settings, server)
    await _run(connector, settings, MemoryPublisher(), expect=count)

    total = _metric(connector, "ingest_lag_seconds_count")
    assert total >= count
    under_ten = _metric(connector, "ingest_lag_seconds_bucket", le="10.0")
    assert under_ten / total >= 0.95, (
        f"nur {under_ten}/{total} Nachrichten unter 10 s - p95 verfehlt"
    )
    # Der Konnektor selbst liegt um Groessenordnungen darunter; die Zusage
    # von 10 s hat Luft fuer die Laufzeit der Quelle.
    under_one = _metric(connector, "ingest_lag_seconds_bucket", le="1.0")
    assert under_one / total >= 0.95


async def test_quality_flags_are_counted(settings, ais_settings, edge_cases) -> None:
    connector = _connector(settings, ais_settings, FakeServer([m for _, m in edge_cases]))
    await _run(connector, settings, MemoryPublisher(), expect=15)
    assert _metric(connector, "aisstream_quality_flags_total", flag="invalid_position") >= 1
    assert _metric(connector, "aisstream_quality_flags_total", flag="future_timestamp") >= 1


async def test_reconnects_are_counted(settings, ais_settings) -> None:
    server = FakeServer(
        [position_message(211331640, 53.5, 8.1, WHEN), CONNECTION_LOST()],
        [position_message(211331641, 53.6, 8.2, WHEN)],
    )
    connector = _connector(settings, ais_settings, server)
    await _run(connector, settings, MemoryPublisher(), expect=2)
    assert _metric(connector, "aisstream_reconnects_total") >= 1


# --- Cursor ----------------------------------------------------------------


async def test_cursor_records_progress_not_a_resume_point(
    settings, ais_settings, stream_messages
) -> None:
    """AISStream hat kein Replay. Der Cursor zaehlt, er setzt nicht fort.

    Der Test haelt die Zusage fest, damit niemand spaeter einen Wiederanlauf
    darauf baut, den es nicht gibt.
    """
    sample = [m for m in stream_messages if m["MessageType"] == "PositionReport"][:20]
    connector = _connector(settings, ais_settings, FakeServer(sample))
    store = MemoryCursorStore()
    await _run(connector, settings, MemoryPublisher(), expect=20, store=store)

    cursor = await store.load(settings.connector_id)
    assert cursor is not None
    assert cursor.value["messages_seen"] >= 20
    assert cursor.value["connections"] == 1
    assert "resume_token" not in cursor.value
