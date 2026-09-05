"""Prozess-Einstieg.

Wenig Logik, aber die eine Entscheidung, die vor dem ersten Netzzugriff
faellt: ohne Schluessel wird gar nicht erst verbunden.
"""

from __future__ import annotations

import pytest
from aisstream.__main__ import EXIT_FATAL_CONFIG, _build_bronze, main

from argus_connector import ConnectorSettings
from argus_connector.bronze import FilesystemObjectStore, S3ObjectStore


@pytest.mark.asyncio
async def test_missing_api_key_exits_before_connecting(monkeypatch) -> None:
    """Ohne Schluessel weist AISStream ab. Es zu versuchen ist unhoeflich
    und aussichtslos - der Prozess endet mit einem eigenen Code, damit ein
    Orchestrator ihn nicht endlos neu startet."""
    monkeypatch.delenv("ARGUS_AIS_API_KEY", raising=False)
    monkeypatch.setenv("ARGUS_AIS_API_KEY", "")
    assert await main() == EXIT_FATAL_CONFIG


def test_bronze_falls_back_to_the_filesystem_visibly(monkeypatch, tmp_path, caplog) -> None:
    """Der Rueckfall ist erlaubt, aber nicht still.

    Ein Rohdatenarchiv, das unbemerkt im Container liegt statt im
    Objektspeicher, ist beim naechsten Neustart weg - und damit der
    Wiederherstellungspfad des Systems.
    """
    monkeypatch.setenv("ARGUS_BRONZE__LOCAL_DIR", str(tmp_path))
    settings = ConnectorSettings(source_id="aisstream")
    with caplog.at_level("WARNING"):
        writer = _build_bronze(settings)
    assert isinstance(writer._store, FilesystemObjectStore)
    assert any("lokal" in record.message for record in caplog.records)


def test_bronze_uses_s3_when_credentials_are_present() -> None:
    settings = ConnectorSettings(
        source_id="aisstream",
        bronze={
            "bucket": "argus-bronze",
            "endpoint_url": "http://minio:9000",
            "access_key": "key",
            "secret_key": "secret",
        },
    )
    assert isinstance(_build_bronze(settings)._store, S3ObjectStore)
