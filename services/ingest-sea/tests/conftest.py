"""Gemeinsame Testhilfen des AIS-Konnektors."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from aisstream.config import AisStreamSettings

from argus_connector import ConnectorSettings

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "aisstream"
STREAM_FILE = FIXTURES / "stream-sample.jsonl"
EDGE_FILE = FIXTURES / "edge-cases.jsonl"


def _load(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise RuntimeError(
            f"Fixture {path} fehlt. Mit 'python tests/tools/make_fixtures.py' erzeugen."
        )
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


@pytest.fixture(scope="session")
def stream_messages() -> list[dict[str, Any]]:
    """Der Hauptbestand, unveraendert."""
    return _load(STREAM_FILE)


@pytest.fixture(scope="session")
def edge_cases() -> list[tuple[str, dict[str, Any]]]:
    """Sonderfaelle als (Beschreibung, Nachricht).

    Der Schluessel `_case` ist Dokumentation und wird hier entfernt - er darf
    nie in den Parser gelangen, sonst testen wir eine Drahtform, die es nicht
    gibt.
    """
    cases = []
    for message in _load(EDGE_FILE):
        description = message.pop("_case", "")
        cases.append((description, message))
    return cases


@pytest.fixture
def edge_case(
    edge_cases: list[tuple[str, dict[str, Any]]],
) -> Callable[[str], dict[str, Any]]:
    """Sucht einen Sonderfall ueber ein Stichwort seiner Beschreibung.

    Als Fixture und nicht als importierbare Funktion: unter services/ gibt es
    mehrere Pakete mit einem Verzeichnis 'tests', und pytest legt sie beim
    Import auf denselben Modulnamen. Ein 'from tests.conftest import ...'
    holt dann je nach Sammelreihenfolge das falsche Modul.
    """

    def find(needle: str) -> dict[str, Any]:
        matches = [
            message for description, message in edge_cases if needle.lower() in description.lower()
        ]
        if len(matches) != 1:
            raise AssertionError(
                f"{len(matches)} Sonderfaelle passen auf {needle!r} - erwartet wird genau einer."
            )
        return matches[0]

    return find


@pytest.fixture
def settings() -> ConnectorSettings:
    return ConnectorSettings(
        connector_id="ingest-sea-aisstream",
        source_id="aisstream",
        connector_version="0.1.0",
        schema_version="1.0.0",
        nats={"subject_prefix": "argus.canon"},
        cursor={"backend": "memory"},
        metrics={"enabled": False},
        # Fuer einen Stromkonnektor gehoert die Wartezeit in fetch(), nicht
        # zwischen die Stapel: fetch() blockiert bereits bis zu
        # max_batch_wait_s auf die naechste Nachricht. Ein Poll-Intervall
        # obendrauf legt den Konnektor nach jedem Stapel schlafen, waehrend
        # die Warteschlange volllaeuft. Der Standardwert von 60 s ist fuer
        # abfragende Quellen gedacht.
        poll_interval_s=0.0,
    )


@pytest.fixture
def ais_settings() -> AisStreamSettings:
    return AisStreamSettings(
        api_key="test-key",
        bounding_boxes=[[[53.0, 6.0], [55.0, 9.0]]],
        max_batch_size=500,
        max_batch_wait_s=0.05,
        queue_size=1000,
        reconnect_base_delay_s=0.01,
        reconnect_max_delay_s=0.05,
    )
