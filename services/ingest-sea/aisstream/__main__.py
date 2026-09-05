"""Prozess-Einstieg: python -m aisstream.

Baut die Teile zusammen und uebergibt an den Runner des SDK. Hier steht keine
Fachlogik - wer wissen will, was der Konnektor tut, liest connector.py.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from aisstream.config import AisStreamSettings
from aisstream.connector import AisStreamConnector
from aisstream.stream import FatalStreamError
from argus_connector import ConnectorRunner, ConnectorSettings, NatsPublisher
from argus_connector.bronze import (
    BronzeWriter,
    FilesystemObjectStore,
    ObjectStore,
    S3ObjectStore,
)
from argus_connector.runner import build_cursor_store

logger = logging.getLogger("aisstream")

# Prozess-Rueckgabewerte. Getrennt, weil ein Neustart bei 2 sinnlos ist:
# ein falscher Schluessel wird durch Wiederholen nicht richtig, und ein
# Orchestrator soll den Unterschied sehen koennen.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_FATAL_CONFIG = 2


def _build_bronze(settings: ConnectorSettings) -> BronzeWriter:
    """Bronze-Ziel nach Konfiguration.

    Ohne Endpunkt und ohne Zugangsdaten wird lokal geschrieben. Das ist fuer
    die Entwicklung richtig und in Produktion falsch - deshalb der Hinweis im
    Protokoll statt eines stillen Rueckfalls.
    """
    store: ObjectStore
    if settings.bronze.access_key and settings.bronze.secret_key:
        store = S3ObjectStore(
            bucket=settings.bronze.bucket,
            endpoint_url=settings.bronze.endpoint_url,
            region=settings.bronze.region,
            access_key=settings.bronze.access_key,
            secret_key=settings.bronze.secret_key,
        )
    else:
        path = os.environ.get("ARGUS_BRONZE__LOCAL_DIR", "/var/lib/argus/bronze")
        logger.warning(
            "Keine S3-Zugangsdaten gesetzt - Bronze wird lokal unter %s abgelegt. "
            "Im Betrieb gehoert das Rohdatenarchiv in den Objektspeicher.",
            path,
        )
        store = FilesystemObjectStore(path)
    return BronzeWriter(
        store,
        source_id=settings.source_id,
        max_records=settings.bronze.max_batch_records,
        max_bytes=settings.bronze.max_batch_bytes,
        max_age_s=settings.bronze.max_batch_age_s,
        compress=settings.bronze.compress,
        spool_dir=settings.bronze.spool_dir,
    )


async def main() -> int:
    logging.basicConfig(
        level=os.environ.get("ARGUS_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
    )

    settings = ConnectorSettings()
    ais_settings = AisStreamSettings()

    if not ais_settings.api_key.get_secret_value():
        logger.error(
            "ARGUS_AIS_API_KEY ist leer. AISStream weist die Verbindung ohne "
            "Schluessel ab; der Prozess startet erst gar nicht."
        )
        return EXIT_FATAL_CONFIG

    connector = AisStreamConnector(settings, ais_settings)
    if settings.metrics.enabled:
        connector.metrics.serve(settings.metrics.host, settings.metrics.port)
        logger.info(
            "Metriken auf http://%s:%d/metrics", settings.metrics.host, settings.metrics.port
        )

    runner = ConnectorRunner(
        connector,
        settings=settings,
        cursor_store=build_cursor_store(settings),
        publisher=NatsPublisher(
            settings.nats.url,
            stream=settings.nats.stream,
            connect_timeout_s=settings.nats.connect_timeout_s,
            ack_timeout_s=settings.nats.ack_timeout_s,
            max_reconnect_attempts=settings.nats.max_reconnect_attempts,
        ),
        bronze=_build_bronze(settings),
    )
    runner.install_signal_handlers()

    try:
        await runner.run()
    except FatalStreamError as exc:
        logger.error("Abbruch: %s", exc)
        return EXIT_FATAL_CONFIG
    return EXIT_OK


def run() -> None:
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(EXIT_OK)


if __name__ == "__main__":
    run()
