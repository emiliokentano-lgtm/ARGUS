"""Testumgebung des Connector SDK.

Was sich ohne Fremdsysteme testen laesst, wird ohne getestet. Cursor-Persistenz
laesst sich das nicht: ob ein Wert einen Prozessabsturz ueberlebt, zeigt nur ein
echter Speicher. Postgres und Valkey werden deshalb als echte Dienste benutzt,
wenn sie erreichbar sind, und die betreffenden Tests sonst uebersprungen -
nicht als bestanden gemeldet.
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = TESTS_DIR.parent
sys.path.insert(0, str(PACKAGE_DIR))


def _reachable(url: str) -> bool:
    """Prueft, ob ein Dienst antwortet, ohne einen Client zu importieren."""
    try:
        if url.startswith(("redis://", "rediss://")):
            rest = url.split("://", 1)[1].split("/", 1)[0]
            host, _, port = rest.partition(":")
            with socket.create_connection((host or "localhost", int(port or 6379)), timeout=1):
                return True
        return False
    except OSError:
        return False


POSTGRES_DSN = os.environ.get("ARGUS_TEST_POSTGRES_DSN", "")
VALKEY_URL = os.environ.get("ARGUS_TEST_VALKEY_URL", "redis://127.0.0.1:6379/9")

requires_postgres = pytest.mark.skipif(
    not POSTGRES_DSN,
    reason="ARGUS_TEST_POSTGRES_DSN nicht gesetzt",
)
requires_valkey = pytest.mark.skipif(
    not _reachable(VALKEY_URL),
    reason=f"Valkey/Redis unter {VALKEY_URL} nicht erreichbar",
)


@pytest.fixture()
def postgres_dsn() -> str:
    if not POSTGRES_DSN:
        pytest.skip("ARGUS_TEST_POSTGRES_DSN nicht gesetzt")
    return POSTGRES_DSN


@pytest.fixture()
def valkey_url() -> str:
    if not _reachable(VALKEY_URL):
        pytest.skip("Valkey nicht erreichbar")
    return VALKEY_URL


@pytest.fixture()
def settings(tmp_path):
    """Konfiguration, die nichts nach draussen tut."""
    from argus_connector.config import ConnectorSettings

    return ConnectorSettings(
        connector_id="test-connector",
        source_id="test-source",
        poll_interval_s=0.01,
        batch_size=10,
        fetch_timeout_s=5.0,
        cursor={"backend": "memory"},
        bronze={"spool_dir": str(tmp_path / "spool")},
        metrics={"enabled": False},
        ratelimit={"requests_per_second": 1000.0, "burst": 1000},
        retry={"max_attempts": 3, "base_delay_s": 0.001, "max_delay_s": 0.01},
    )


@pytest.fixture()
def metrics():
    from prometheus_client import CollectorRegistry

    from argus_connector.metrics import ConnectorMetrics

    return ConnectorMetrics("test-connector", "test-source", registry=CollectorRegistry())


class ManualClock:
    """Steuerbare Uhr fuer Zeittests - schneller und verlaesslicher als sleep."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    @property
    def total_slept(self) -> float:
        return sum(self.slept)


@pytest.fixture()
def clock() -> ManualClock:
    return ManualClock()
