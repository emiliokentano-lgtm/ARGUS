"""Konnektorprozess fuer den Absturztest.

Wird als eigenstaendiger Prozess gestartet und mit SIGKILL getoetet - deshalb
ein eigenes Skript und kein Thread: nur ein echter Prozessabbruch beweist, dass
die Wiederaufnahme haelt.

Der Publisher schreibt jede veroeffentlichte Nachricht als eine Zeile in eine
Datei und ruft fsync auf. Das ist die Rolle des Busses im Test: was in der Datei
steht, ist zugestellt; was fehlt, ist verloren. Bewusst OHNE Deduplizierung,
damit der Test Doppelzustellungen zaehlen kann statt sie zu verstecken.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from argus_connector.base import BaseConnector, CanonicalMessage, FetchResult, RawRecord
from argus_connector.bronze import BronzeWriter, FilesystemObjectStore
from argus_connector.bus import PublishResult
from argus_connector.config import ConnectorSettings
from argus_connector.cursor import PostgresCursorStore
from argus_connector.runner import ConnectorRunner


class AppendingPublisher:
    """Schreibt Zustellungen dauerhaft in eine Datei."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle = None

    async def connect(self) -> None:
        self._handle = self._path.open("a", encoding="utf-8")

    async def publish(self, subject, payload, *, dedupe_key) -> bool:
        self._handle.write(f"{payload['id']}\t{dedupe_key}\n")
        return True

    async def publish_batch(self, messages) -> PublishResult:
        for subject, payload, dedupe_key in messages:
            await self.publish(subject, payload, dedupe_key=dedupe_key)
        # Erst nach dem Flush gilt der Batch als zugestellt - genau wie eine
        # JetStream-Bestaetigung.
        self._handle.flush()
        os.fsync(self._handle.fileno())
        return PublishResult(published=len(messages))

    async def close(self) -> None:
        if self._handle is not None:
            self._handle.flush()
            os.fsync(self._handle.fileno())
            self._handle.close()
            self._handle = None


class PagedConnector(BaseConnector):
    dedupe_fields = ("id",)

    def __init__(self, settings, *, source_url: str, page: int) -> None:
        super().__init__(settings)
        self._source_url = source_url
        self._page = page

    async def fetch(self, cursor):
        data = await self.get_json(
            f"{self._source_url}/records",
            params={"cursor": int(cursor or 0), "limit": self._page},
        )
        records = [
            RawRecord(payload=item, source_timestamp=float(item["ts"])) for item in data["records"]
        ]
        return FetchResult(
            records=records,
            next_cursor=data["next_cursor"],
            has_more=bool(data["has_more"]),
        )

    def normalize(self, raw):
        return [
            CanonicalMessage(
                subject_suffix="mock",
                payload=raw.payload,
                dedupe_key=self.dedupe_key_for(raw.payload),
                observed_at=float(raw.payload["ts"]),
            )
        ]


async def main() -> int:
    settings = ConnectorSettings(
        connector_id=os.environ["CONNECTOR_ID"],
        source_id="mock-source",
        poll_interval_s=0.01,
        fetch_timeout_s=10.0,
        cursor={"backend": "postgres", "postgres_dsn": os.environ["CURSOR_DSN"]},
        metrics={"enabled": False},
        ratelimit={"requests_per_second": 1000.0, "burst": 1000},
        retry={"max_attempts": 3, "base_delay_s": 0.01, "max_delay_s": 0.1},
    )
    connector = PagedConnector(
        settings,
        source_url=os.environ["SOURCE_URL"],
        page=int(os.environ.get("PAGE_SIZE", "25")),
    )
    bronze = BronzeWriter(
        FilesystemObjectStore(os.environ["BRONZE_DIR"]),
        source_id="mock-source",
        max_records=int(os.environ.get("PAGE_SIZE", "25")),
        compress=False,
        spool_dir=os.environ["BRONZE_DIR"] + "-spool",
    )
    runner = ConnectorRunner(
        connector,
        settings=settings,
        cursor_store=PostgresCursorStore(os.environ["CURSOR_DSN"], schema="argus_connector_test"),
        publisher=AppendingPublisher(Path(os.environ["OUTPUT_FILE"])),
        bronze=bronze,
    )
    runner.install_signal_handlers()

    total = int(os.environ["TOTAL_RECORDS"])
    page = int(os.environ.get("PAGE_SIZE", "25"))
    # Genug Batches fuer den ganzen Bestand, dann beenden.
    await runner.run(max_batches=(total // page) + 2)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
