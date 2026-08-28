"""Bitemporale Versionierung: was wussten wir wann."""

from __future__ import annotations

import time

import pytest

from conftest import requires_db

pytestmark = requires_db


@pytest.fixture()
def event_with_history(conn):
    """Ein Ereignis in drei Fassungen, mit Zeitmarken dazwischen."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO argus.sources (source_id, schema_version, name, license_id, reliability) "
            "VALUES ('bitemporal-test', '1.0.0', 'Test', 'test-license', 'a') "
            "ON CONFLICT DO NOTHING"
        )
        cur.execute(
            """
            INSERT INTO argus.events (event_id, schema_version, type, title, summary, lang,
                occurred_start, occurred_precision, severity, confidence, status,
                source_id, independent_sources, first_seen_source, version)
            VALUES ('01EVBT', '1.0.0', 'economic.rate_decision', 'Leitzinsentscheid',
                    'Erste Meldung.', 'de', '2026-08-28T12:15:00Z', 'minute',
                    0.50, 0.60, 'reported', 'bitemporal-test', 1, 'reuters', 1)
            """
        )
        time.sleep(0.02)
        cur.execute("SELECT clock_timestamp()")
        t_after_v1 = cur.fetchone()[0]
        time.sleep(0.02)

        cur.execute(
            "UPDATE argus.events SET severity = 0.72, confidence = 0.95, "
            "status = 'confirmed', independent_sources = 6, "
            "summary = 'Von sechs Quellen bestaetigt.', version = 2 "
            "WHERE event_id = '01EVBT'"
        )
        time.sleep(0.02)
        cur.execute("SELECT clock_timestamp()")
        t_after_v2 = cur.fetchone()[0]
        time.sleep(0.02)

        cur.execute(
            "UPDATE argus.events SET status = 'retracted', retracted_at = now(), "
            "retraction_reason = 'Quelle hat widerrufen', version = 3 "
            "WHERE event_id = '01EVBT'"
        )
    yield t_after_v1, t_after_v2
    conn.rollback()


def as_of(conn, at):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT version, status, severity, confidence, summary "
            "FROM argus.event_as_of('01EVBT', %s)",
            (at,),
        )
        return cur.fetchall()


def test_state_at_t1_is_the_first_version(conn, event_with_history):
    t1, _ = event_with_history
    rows = as_of(conn, t1)
    assert len(rows) == 1, "zu jedem Zeitpunkt darf es genau eine Fassung geben"
    version, status, severity, confidence, summary = rows[0]
    assert (version, status) == (1, "reported")
    assert severity == pytest.approx(0.50)
    assert confidence == pytest.approx(0.60)
    assert summary == "Erste Meldung."


def test_state_at_t2_is_the_confirmed_version(conn, event_with_history):
    _, t2 = event_with_history
    rows = as_of(conn, t2)
    assert len(rows) == 1
    version, status, severity, _, summary = rows[0]
    assert (version, status) == (2, "confirmed")
    assert severity == pytest.approx(0.72)
    assert summary == "Von sechs Quellen bestaetigt."


def test_current_state_is_the_retraction(conn, event_with_history):
    with conn.cursor() as cur:
        cur.execute("SELECT clock_timestamp()")
        now = cur.fetchone()[0]
    rows = as_of(conn, now)
    assert len(rows) == 1
    version, status, *_ = rows[0]
    assert (version, status) == (3, "retracted")


def test_retraction_does_not_delete_content(conn, event_with_history):
    """Ein Rueckzug loescht nichts - er ergaenzt Status und Begruendung."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT title, summary, retraction_reason FROM argus.events "
            "WHERE event_id = '01EVBT'"
        )
        title, summary, reason = cur.fetchone()
    assert title == "Leitzinsentscheid"
    assert summary
    assert reason == "Quelle hat widerrufen"


def test_history_is_gapless_and_non_overlapping(conn, event_with_history):
    """Die sys_period-Intervalle reihen sich lueckenlos aneinander.

    Nur so ist garantiert, dass eine Zeitreise fuer jeden Zeitpunkt genau eine
    Antwort liefert - weder keine noch zwei.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT lower(sys_period), upper(sys_period)
              FROM (
                SELECT sys_period FROM argus.events WHERE event_id = '01EVBT'
                UNION ALL
                SELECT sys_period FROM argus.events_history WHERE event_id = '01EVBT'
              ) s
             ORDER BY lower(sys_period)
            """
        )
        periods = cur.fetchall()

    assert len(periods) == 3
    for (_, prev_upper), (next_lower, _) in zip(periods, periods[1:]):
        assert prev_upper == next_lower, "Luecke oder Ueberlappung in der Versionskette"
    assert periods[-1][1] is None, "die aktuelle Fassung hat ein offenes Ende"


def test_query_before_creation_returns_nothing(conn, event_with_history):
    """Vor der Erstanlage existierte das Ereignis nicht - und das System soll
    nicht so tun, als haette es damals schon davon gewusst."""
    rows = as_of(conn, "2020-01-01T00:00:00Z")
    assert rows == []


def test_history_table_is_not_written_directly(conn, event_with_history):
    """Die Verlaufstabelle enthaelt genau die abgeloesten Fassungen."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*), count(*) FILTER (WHERE upper(sys_period) IS NULL) "
            "FROM argus.events_history WHERE event_id = '01EVBT'"
        )
        total, open_ended = cur.fetchone()
    assert total == 2
    assert open_ended == 0, "eine historische Fassung darf kein offenes Ende haben"


def test_entities_are_versioned_too(conn):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO argus.entities (entity_id, schema_version, type, display_name) "
            "VALUES ('01ENTBT', '1.0.0', 'vessel', 'Alter Name')"
        )
        cur.execute(
            "UPDATE argus.entities SET display_name = 'Neuer Name', version = 2 "
            "WHERE entity_id = '01ENTBT'"
        )
        cur.execute(
            "SELECT display_name FROM argus.entities_history WHERE entity_id = '01ENTBT'"
        )
        assert cur.fetchone()[0] == "Alter Name"
    conn.rollback()
