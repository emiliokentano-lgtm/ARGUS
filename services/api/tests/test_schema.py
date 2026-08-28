"""Zusicherungen ueber das Schema und seine Randbedingungen."""

from __future__ import annotations

import psycopg
import pytest
from conftest import requires_db

pytestmark = requires_db


# --- Invarianten ------------------------------------------------------------


def test_schema_invariants_hold(conn):
    """Zeitzonenfalle und Fremdschluessel ohne ON DELETE sind ausgeschlossen."""
    with conn.cursor() as cur:
        cur.execute("SELECT invariant, holds FROM argus.schema_invariants")
        results = dict(cur.fetchall())
    failing = [name for name, holds in results.items() if not holds]
    assert not failing, f"verletzte Invarianten: {failing}"
    assert set(results) == {"no_naive_timestamps", "all_fks_have_delete_rule"}


def test_no_naive_timestamp_columns(conn):
    """Die Zusicherungsfunktion muss ohne Fehler durchlaufen."""
    with conn.cursor() as cur:
        cur.execute("SELECT argus.assert_no_naive_timestamps()")


def test_every_timestamp_column_is_timestamptz(conn):
    """Doppelt gepruefte Zeitzonenfalle - direkt am Katalog."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name, column_name, data_type
              FROM information_schema.columns
             WHERE table_schema = 'argus'
               AND data_type LIKE 'timestamp%'
               AND data_type <> 'timestamp with time zone'
            """
        )
        assert cur.fetchall() == []


def test_observations_is_partitioned_by_time(conn):
    """Egal ob Hypertable oder native Partitionierung: nach Zeit partitioniert."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM pg_class c
              JOIN pg_inherits i ON i.inhparent = c.oid
             WHERE c.oid = 'argus.observations'::regclass
            """
        )
        native_partitions = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM pg_extension WHERE extname = 'timescaledb'")
        has_timescale = cur.fetchone()[0] > 0
    assert native_partitions > 0 or has_timescale, (
        "observations ist weder Hypertable noch nativ partitioniert"
    )


def test_entity_time_index_exists(conn):
    """Der Index, auf dem die haeufigste Abfrage der Track-Engine sitzt."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT indexdef FROM pg_indexes
             WHERE schemaname = 'argus' AND tablename = 'observations'
               AND indexname = 'observations_entity_time_idx'
            """
        )
        row = cur.fetchone()
    assert row is not None
    assert "entity_id" in row[0] and "observed_at DESC" in row[0]


# --- Alias-Eindeutigkeit ----------------------------------------------------


def test_duplicate_alias_is_rejected(conn):
    """Derselbe Bezeichner darf nie auf zwei Entitaeten zeigen."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO argus.entities (entity_id, schema_version, type, display_name) "
            "VALUES ('01TESTALIASA', '1.0.0', 'vessel', 'A'), "
            "       ('01TESTALIASB', '1.0.0', 'vessel', 'B')"
        )
        cur.execute(
            "INSERT INTO argus.entity_aliases (entity_id, id_type, id_value) "
            "VALUES ('01TESTALIASA', 'imo', '9284435')"
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO argus.entity_aliases (entity_id, id_type, id_value) "
                "VALUES ('01TESTALIASB', 'imo', '9284435')"
            )
    conn.rollback()


def test_same_value_different_id_type_is_allowed(conn):
    """Die Eindeutigkeit gilt je Bezeichnerart, nicht global."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO argus.entities (entity_id, schema_version, type, display_name) "
            "VALUES ('01TESTALIASC', '1.0.0', 'vessel', 'C')"
        )
        cur.execute(
            "INSERT INTO argus.entity_aliases (entity_id, id_type, id_value) VALUES "
            "('01TESTALIASC', 'imo', '1234567'), ('01TESTALIASC', 'mmsi', '1234567')"
        )
    conn.rollback()


# --- Geo-Praezision ---------------------------------------------------------


def _insert_source(cur, source_id="testsource"):
    cur.execute(
        "INSERT INTO argus.sources (source_id, schema_version, name, license_id) "
        "VALUES (%s, '1.0.0', 'Test', 'test-license') ON CONFLICT DO NOTHING",
        (source_id,),
    )


def test_country_precision_point_must_be_marked_derived(conn):
    """Ein Punkt bei Landgenauigkeit muss als abgeleitet gekennzeichnet sein.

    Genau das verhindert die Landesmitte, die wie eine Messung aussieht.
    """
    with conn.cursor() as cur:
        _insert_source(cur)
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO argus.events (event_id, schema_version, type, title,
                                          occurred_start, geo_point, geo_precision,
                                          geo_point_is_derived, source_id)
                VALUES ('01EVGEOBAD', '1.0.0', 'civil.strike', 'Test',
                        now(), 'SRID=4326;POINT(-63.6 -38.4)', 'country',
                        false, 'testsource')
                """
            )
    conn.rollback()


def test_country_precision_with_derived_flag_is_allowed(conn):
    with conn.cursor() as cur:
        _insert_source(cur)
        cur.execute(
            """
            INSERT INTO argus.events (event_id, schema_version, type, title,
                                      occurred_start, geo_point, geo_precision,
                                      geo_point_is_derived, source_id)
            VALUES ('01EVGEOOK', '1.0.0', 'civil.strike', 'Test',
                    now(), 'SRID=4326;POINT(-63.6 -38.4)', 'country',
                    true, 'testsource')
            """
        )
    conn.rollback()


def test_exact_precision_point_needs_no_flag(conn):
    with conn.cursor() as cur:
        _insert_source(cur)
        cur.execute(
            """
            INSERT INTO argus.events (event_id, schema_version, type, title,
                                      occurred_start, geo_point, geo_precision, source_id)
            VALUES ('01EVGEOEX', '1.0.0', 'natural.earthquake', 'Test',
                    now(), 'SRID=4326;POINT(8.67 50.11)', 'exact', 'testsource')
            """
        )
    conn.rollback()


# --- Beobachtungen ----------------------------------------------------------


def _insert_observation(cur, **overrides):
    values = {
        "obs_id": "01OBSTEST",
        "observed_at": "now()",
        "ingested_at": "now()",
        "time_quality": "'source_provided'",
        "is_dead_reckoned": "false",
        "uncertainty_radius_m": "NULL",
        "kind": "'position'",
        "geo": "'SRID=4326;POINT(56.26 25.94)'",
    }
    values.update(overrides)
    # Die eingesetzten Werte stammen ausschliesslich aus dieser Datei. Ein
    # Test, der sie als Parameter uebergibt, koennte die CHECK-Constraint
    # nicht verletzen - genau darum geht es hier aber.
    cur.execute(
        f"""
        INSERT INTO argus.observations (obs_id, schema_version, ref_type, ref_id, kind,
            observed_at, time_quality, ingested_at, source_id, geo, geo_precision,
            is_dead_reckoned, uncertainty_radius_m, dedupe_key)
        VALUES ('{values["obs_id"]}', '1.0.0', 'vessel', 'mmsi:1', {values["kind"]},
                {values["observed_at"]}, {values["time_quality"]}, {values["ingested_at"]},
                'testsource', {values["geo"]}, 'exact',
                {values["is_dead_reckoned"]}, {values["uncertainty_radius_m"]},
                '{values["obs_id"]}-key')
        """
    )


def test_inferred_timestamp_must_equal_ingested_at(conn):
    """Ein eingesetzter Ersatzzeitstempel darf nicht wie eine Messung aussehen."""
    with conn.cursor() as cur:
        _insert_source(cur)
        with pytest.raises(psycopg.errors.CheckViolation):
            _insert_observation(
                cur,
                obs_id="01OBSBADTIME",
                observed_at="now() - interval '1 hour'",
                time_quality="'inferred_from_ingest'",
            )
    conn.rollback()


def test_dead_reckoned_position_needs_uncertainty(conn):
    """Eine berechnete Position ohne Unsicherheitsangabe ist ein Punkt, der
    Gewissheit vortaeuscht."""
    with conn.cursor() as cur:
        _insert_source(cur)
        with pytest.raises(psycopg.errors.CheckViolation):
            _insert_observation(cur, obs_id="01OBSBADDR", is_dead_reckoned="true")
    conn.rollback()


def test_position_observation_requires_geometry(conn):
    with conn.cursor() as cur:
        _insert_source(cur)
        with pytest.raises(psycopg.errors.CheckViolation):
            _insert_observation(cur, obs_id="01OBSNOGEO", geo="NULL")
    conn.rollback()


def test_deleting_entity_keeps_observation_and_raw_reference(conn):
    """ON DELETE SET NULL: eine geloeschte Entitaet vernichtet keine
    Beobachtungen, und die Rohaussage der Quelle bleibt aufloesbar."""
    with conn.cursor() as cur:
        _insert_source(cur)
        cur.execute(
            "INSERT INTO argus.entities (entity_id, schema_version, type, display_name) "
            "VALUES ('01ENTDEL', '1.0.0', 'vessel', 'Zu loeschen')"
        )
        cur.execute(
            """
            INSERT INTO argus.observations (obs_id, schema_version, entity_id, ref_type,
                ref_id, kind, observed_at, ingested_at, source_id, geo, dedupe_key)
            VALUES ('01OBSDEL', '1.0.0', '01ENTDEL', 'vessel', 'mmsi:99', 'position',
                    now(), now(), 'testsource', 'SRID=4326;POINT(1 1)', '01OBSDEL-key')
            """
        )
        cur.execute("DELETE FROM argus.entities WHERE entity_id = '01ENTDEL'")
        cur.execute("SELECT entity_id, ref_id FROM argus.observations WHERE obs_id = '01OBSDEL'")
        entity_id, ref_id = cur.fetchone()
    assert entity_id is None
    assert ref_id == "mmsi:99"
    conn.rollback()


# --- Bewertungen ------------------------------------------------------------


def test_model_assessment_requires_provenance(conn):
    """Kapitel 11: ohne Modellversion und Prompt-Hash kein Modell-Output."""
    with conn.cursor() as cur, pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            """
                INSERT INTO argus.assessments (assessment_id, schema_version, kind,
                    subject_kind, subject_id, statement, confidence, author_type,
                    author_id, owner_id, evidence)
                VALUES ('01ASBAD', '1.0.0', 'hypothesis', 'event', '01EV', 'Behauptung',
                        0.6, 'model', 'model:x', 'user:1', '[{"kind":"report","ref":"r1"}]')
                """
        )
    conn.rollback()


def test_machine_assessment_requires_evidence(conn):
    with conn.cursor() as cur, pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            """
                INSERT INTO argus.assessments (assessment_id, schema_version, kind,
                    subject_kind, subject_id, statement, confidence, author_type,
                    author_id, owner_id, model, model_version, prompt_hash, evidence)
                VALUES ('01ASNOEV', '1.0.0', 'hypothesis', 'event', '01EV', 'Behauptung',
                        0.6, 'model', 'model:x', 'user:1', 'llama', '3.1', 'abc', '[]')
                """
        )
    conn.rollback()


# --- Alarmhygiene -----------------------------------------------------------


def test_only_one_open_alert_per_dedupe_key(conn):
    """Derselbe Sachverhalt erzeugt keinen zweiten offenen Alarm."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO argus.alerts (alert_id, schema_version, rule_id, rule_version,
                severity, status, title, dedupe_key)
            VALUES ('01ALA', '1.0.0', 'r1', 'v1', 'alert', 'new', 'Erster', 'dk-1')
            """
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute(
                """
                INSERT INTO argus.alerts (alert_id, schema_version, rule_id, rule_version,
                    severity, status, title, dedupe_key)
                VALUES ('01ALB', '1.0.0', 'r1', 'v1', 'alert', 'new', 'Zweiter', 'dk-1')
                """
            )
    conn.rollback()


def test_closed_alert_frees_the_dedupe_key(conn):
    """Nach dem Abschluss darf derselbe Sachverhalt wieder alarmieren."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO argus.alerts (alert_id, schema_version, rule_id, rule_version,
                severity, status, title, dedupe_key, resolved_at, resolved_by,
                resolution_disposition)
            VALUES ('01ALC', '1.0.0', 'r1', 'v1', 'alert', 'resolved', 'Alt', 'dk-2',
                    now(), 'user:1', 'true_positive')
            """
        )
        cur.execute(
            """
            INSERT INTO argus.alerts (alert_id, schema_version, rule_id, rule_version,
                severity, status, title, dedupe_key)
            VALUES ('01ALD', '1.0.0', 'r1', 'v1', 'alert', 'new', 'Neu', 'dk-2')
            """
        )
    conn.rollback()
