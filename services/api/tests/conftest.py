"""Testumgebung fuer die ARGUS-Migrationen.

Die Tests laufen gegen eine echte PostgreSQL-Datenbank - ein Schema mit
PostGIS-Typen, Triggern, generierten Spalten und Row-Level Security laesst sich
nicht sinnvoll gegen SQLite oder ein Mock pruefen.

    export DATABASE_URL='postgresql://argus:argus@localhost:5432/argus_test'
    pytest

Ohne DATABASE_URL werden die Tests uebersprungen, nicht als bestanden gemeldet.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parent.parent


def _url() -> str | None:
    url = os.environ.get("DATABASE_URL", "").strip()
    return url or None


requires_db = pytest.mark.skipif(
    _url() is None,
    reason="DATABASE_URL nicht gesetzt - Migrationstests brauchen eine echte Datenbank",
)


def run_alembic(*args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_DIR,
        env=env,
        capture_output=True,
        text=True,
        # Der Rueckgabewert wird im Test geprueft - ein Fehlschlag ist
        # oft genau das, was der Test erwartet.
        check=False,
    )


@pytest.fixture(scope="session")
def db_url() -> str:
    url = _url()
    if url is None:
        pytest.skip("DATABASE_URL nicht gesetzt")
    return url.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture(scope="session")
def migrated(db_url: str) -> str:
    """Bringt die Datenbank auf den aktuellen Stand."""
    result = run_alembic("upgrade", "head")
    assert result.returncode == 0, f"alembic upgrade head fehlgeschlagen:\n{result.stderr}"
    return db_url


@pytest.fixture()
def conn(migrated: str):
    import psycopg

    connection = psycopg.connect(migrated)
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()
