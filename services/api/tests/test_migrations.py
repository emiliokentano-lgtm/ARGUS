"""Migrationen vorwaerts, rueckwaerts und unter widrigen Umstaenden.

Diese Tests arbeiten auf einer eigenen Wegwerf-Datenbank, damit ein
downgrade nicht den Bestand der uebrigen Tests loescht.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest
from conftest import requires_db, run_alembic
from psycopg import sql

pytestmark = requires_db


@pytest.fixture()
def scratch_db(db_url: str):
    """Legt eine leere Datenbank an und raeumt sie hinterher weg."""
    name = f"argus_mig_{uuid.uuid4().hex[:8]}"
    admin = psycopg.connect(db_url, autocommit=True)
    try:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    finally:
        admin.close()

    scratch_url = _with_dbname(db_url, name)
    with psycopg.connect(scratch_url) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        conn.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        conn.commit()

    try:
        yield scratch_url
    finally:
        admin = psycopg.connect(db_url, autocommit=True)
        try:
            admin.execute(
                sql.SQL(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()"
                ),
                (name,),
            )
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
        finally:
            admin.close()


def _with_dbname(url: str, name: str) -> str:
    head, _, tail = url.partition("://")
    creds, _, rest = tail.partition("/")
    _path, sep, query = rest.partition("?")
    return f"{head}://{creds}/{name}{sep}{query}"


def _count_tables(url: str) -> int:
    with psycopg.connect(url) as conn:
        return conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'argus'"
        ).fetchone()[0]


def test_upgrade_then_downgrade_to_base(scratch_db):
    """Beide Richtungen laufen vollstaendig durch."""
    env = {"DATABASE_URL": scratch_db}
    up = run_alembic("upgrade", "head", env_extra=env)
    assert up.returncode == 0, up.stderr
    assert _count_tables(scratch_db) > 30

    down = run_alembic("downgrade", "base", env_extra=env)
    assert down.returncode == 0, down.stderr
    assert _count_tables(scratch_db) == 0

    with psycopg.connect(scratch_db) as conn:
        remaining = conn.execute(
            "SELECT count(*) FROM pg_namespace WHERE nspname = 'argus'"
        ).fetchone()[0]
    assert remaining == 0, "das Schema argus muss nach downgrade base verschwunden sein"


def test_upgrade_downgrade_cycle_is_repeatable(scratch_db):
    env = {"DATABASE_URL": scratch_db}
    for round_number in range(2):
        assert run_alembic("upgrade", "head", env_extra=env).returncode == 0, round_number
        assert run_alembic("downgrade", "base", env_extra=env).returncode == 0, round_number


def test_each_migration_can_be_stepped_individually(scratch_db):
    """Jede Migration einzeln vor und zurueck - findet Abhaengigkeiten, die im
    Gesamtlauf durch Zufall funktionieren."""
    env = {"DATABASE_URL": scratch_db}
    assert run_alembic("upgrade", "head", env_extra=env).returncode == 0
    for _ in range(8):
        result = run_alembic("downgrade", "-1", env_extra=env)
        assert result.returncode == 0, result.stderr
    assert _count_tables(scratch_db) == 0


def test_downgrade_refuses_to_drop_populated_tables(scratch_db):
    """Fehlerfall 'Rollback mit bereits geschriebenen Daten'."""
    env = {"DATABASE_URL": scratch_db}
    assert run_alembic("upgrade", "head", env_extra=env).returncode == 0

    with psycopg.connect(scratch_db) as conn:
        conn.execute(
            "INSERT INTO argus.sources (source_id, schema_version, name, license_id) "
            "VALUES ('s1', '1.0.0', 'Quelle', 'lic')"
        )
        conn.execute(
            "INSERT INTO argus.entities (entity_id, schema_version, type, display_name) "
            "VALUES ('01E', '1.0.0', 'vessel', 'Schiff')"
        )
        conn.commit()

    blocked = run_alembic("downgrade", "0001", env_extra=env)
    assert blocked.returncode != 0
    assert "wuerde Tabellen mit Daten loeschen" in blocked.stderr
    assert "argus.entities: 1 Zeilen" in blocked.stderr
    # Die Daten sind noch da.
    with psycopg.connect(scratch_db) as conn:
        assert conn.execute("SELECT count(*) FROM argus.entities").fetchone()[0] == 1

    allowed = run_alembic(
        "downgrade",
        "0001",
        env_extra={**env, "ARGUS_ALLOW_DESTRUCTIVE_DOWNGRADE": "1"},
    )
    assert allowed.returncode == 0, allowed.stderr


def test_migration_on_foreign_populated_database_is_refused(scratch_db):
    """Fehlerfall 'Migration auf nicht-leerer Datenbank'.

    Ein bestehendes argus-Schema ohne alembic_version bedeutet: hier hat jemand
    anders gearbeitet.
    """
    with psycopg.connect(scratch_db) as conn:
        conn.execute("CREATE SCHEMA argus")
        conn.execute("CREATE TABLE argus.fremde_tabelle (id int)")
        conn.commit()

    result = run_alembic("upgrade", "head", env_extra={"DATABASE_URL": scratch_db})
    assert result.returncode != 0
    assert "nicht von Alembic" in result.stderr
    assert "alembic stamp head" in result.stderr

    forced = run_alembic(
        "-x",
        "force_existing=1",
        "upgrade",
        "head",
        env_extra={"DATABASE_URL": scratch_db},
    )
    assert forced.returncode == 0, forced.stderr


def test_missing_extension_is_reported_with_guidance(db_url):
    """Fehlerfall 'fehlende Extension' - mit Handlungsanweisung."""
    name = f"argus_noext_{uuid.uuid4().hex[:8]}"
    admin = psycopg.connect(db_url, autocommit=True)
    try:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    finally:
        admin.close()
    url = _with_dbname(db_url, name)
    try:
        result = run_alembic("upgrade", "head", env_extra={"DATABASE_URL": url})
        assert result.returncode != 0
        assert "Pflicht-Erweiterungen fehlen" in result.stderr
        assert "postgis" in result.stderr
    finally:
        admin = psycopg.connect(db_url, autocommit=True)
        try:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
        finally:
            admin.close()


def test_timescale_required_but_unavailable_gives_guidance(scratch_db):
    """ARGUS_TIMESCALE=on ohne TimescaleDB: klare Meldung statt Syntaxfehler."""
    with psycopg.connect(scratch_db) as conn:
        available = conn.execute(
            "SELECT count(*) FROM pg_available_extensions WHERE name = 'timescaledb'"
        ).fetchone()[0]
    if available:
        pytest.skip("TimescaleDB ist verfuegbar - dieser Fehlerfall tritt hier nicht auf")

    result = run_alembic(
        "upgrade",
        "head",
        env_extra={"DATABASE_URL": scratch_db, "ARGUS_TIMESCALE": "on"},
    )
    assert result.returncode != 0
    assert "TimescaleDB ist verlangt" in result.stderr
    assert "ARGUS_TIMESCALE=off" in result.stderr
