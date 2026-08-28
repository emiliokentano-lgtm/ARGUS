"""Bronze-Archivierung: jede Rohantwort unveraendert, gebuendelt.

Kapitel 5.2 verlangt, dass jede Rohantwort im Objektspeicher landet,
partitioniert nach source/yyyy/mm/dd/hh. Naiv umgesetzt waere das ein
PUT je Nachricht - bei AIS mit einigen hundert Nachrichten pro Sekunde also
Millionen winziger Objekte pro Tag. Das ist teuer, langsam und macht jede
spaetere Auswertung unbrauchbar.

Deshalb: puffern und buendeln. Ziel ist eine Datei je Quelle und Stunde.
Geschrieben wird, sobald eine dieser Grenzen erreicht ist:

* die Stunde wechselt (Partitionsgrenze)
* der Puffer ueberschreitet max_batch_records oder max_batch_bytes
* der aelteste Satz im Puffer ist aelter als max_batch_age_s
* der Prozess faehrt herunter

Ist der Objektspeicher nicht erreichbar, wandert das Buendel in ein lokales
Spool-Verzeichnis und wird spaeter nachgereicht. Bronze darf nie verloren
gehen - alles andere im System ist daraus wiederherstellbar, Bronze nicht.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import time
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class ObjectStore(Protocol):
    async def put(self, key: str, body: bytes, *, content_type: str) -> None: ...
    async def close(self) -> None: ...


class FilesystemObjectStore:
    """Objektspeicher auf der lokalen Platte.

    Fuer die Entwicklung und fuer Tests. Legt dieselbe Schluesselstruktur an
    wie S3, damit ein Wechsel nichts anderes bedeutet als eine andere
    Konfiguration.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    async def put(self, key: str, body: bytes, *, content_type: str) -> None:
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        # Erst daneben schreiben, dann umbenennen: ein abgebrochener Schreib-
        # vorgang hinterlaesst keine halbe Datei, die wie ein Buendel aussieht.
        tmp = target.with_suffix(target.suffix + ".part")
        await asyncio.to_thread(tmp.write_bytes, body)
        await asyncio.to_thread(os.replace, tmp, target)

    async def close(self) -> None:
        return None


class S3ObjectStore:
    """S3-kompatibler Objektspeicher (MinIO, AWS).

    botocore ist synchron. Die Aufrufe laufen deshalb in einem Thread - das
    blockiert die Ereignisschleife nicht. Ein eigener asynchroner S3-Client
    waere eine weitere Abhaengigkeit fuer einen Aufruf pro Stunde und Quelle;
    das lohnt nicht.
    """

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        region: str = "us-east-1",
        access_key: str | None = None,
        secret_key: str | None = None,
        client: Any = None,
    ) -> None:
        self.bucket = bucket
        self._endpoint_url = endpoint_url
        self._region = region
        self._access_key = access_key
        self._secret_key = secret_key
        self._client = client

    def _get_client(self):
        if self._client is None:
            import boto3  # lokal importiert: optionale Abhaengigkeit

            self._client = boto3.client(
                "s3",
                endpoint_url=self._endpoint_url,
                region_name=self._region,
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
            )
        return self._client

    async def put(self, key: str, body: bytes, *, content_type: str) -> None:
        client = self._get_client()
        await asyncio.to_thread(
            client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )

    async def close(self) -> None:
        return None


class BronzeWriter:
    """Gepufferter, gebuendelter Schreiber fuer den Bronze-Layer."""

    def __init__(
        self,
        store: ObjectStore,
        *,
        source_id: str,
        connector_id: str = "",
        max_records: int = 50_000,
        max_bytes: int = 64 * 1024 * 1024,
        max_age_s: float = 3600.0,
        compress: bool = True,
        spool_dir: str | Path | None = None,
        clock: Callable[[], float] = time.time,
        on_flush: Callable[[str], None] | None = None,
        on_buffer_size: Callable[[int], None] | None = None,
    ) -> None:
        self._store = store
        self.source_id = source_id
        self.connector_id = connector_id
        self.max_records = max_records
        self.max_bytes = max_bytes
        self.max_age_s = max_age_s
        self.compress = compress
        self._spool_dir = Path(spool_dir) if spool_dir else None
        self._clock = clock
        self._on_flush = on_flush
        self._on_buffer_size = on_buffer_size

        self._buffer: list[bytes] = []
        self._buffer_bytes = 0
        self._oldest_at: float | None = None
        self._partition: str | None = None
        self._lock = asyncio.Lock()

        self.flushed_batches = 0
        self.flushed_records = 0
        self.spooled_batches = 0

    # -- Schluessel und Partition ----------------------------------------

    def _partition_for(self, ts: float) -> str:
        dt = datetime.fromtimestamp(ts, tz=UTC)
        return f"{self.source_id}/{dt:%Y/%m/%d/%H}"

    def _object_key(self, partition: str, first_ts: float) -> str:
        dt = datetime.fromtimestamp(first_ts, tz=UTC)
        suffix = ".jsonl.gz" if self.compress else ".jsonl"
        # Zeit plus Zufallsanteil: zwei Prozesse derselben Quelle
        # ueberschreiben einander nicht.
        return f"{partition}/{dt:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}{suffix}"

    # -- Puffern ----------------------------------------------------------

    @property
    def buffered_records(self) -> int:
        return len(self._buffer)

    async def add(self, record: Any, *, fetched_at: float | None = None) -> None:
        """Nimmt einen Rohsatz auf. Schreibt, wenn eine Grenze erreicht ist."""
        ts = fetched_at if fetched_at is not None else self._clock()
        partition = self._partition_for(ts)

        line = (
            record
            if isinstance(record, bytes)
            else json.dumps(record, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
        ) + b"\n"

        async with self._lock:
            # Stundenwechsel: erst das alte Buendel schliessen, damit eine
            # Datei nie zwei Partitionen enthaelt.
            if self._partition is not None and partition != self._partition:
                await self._flush_locked(reason="partition_rollover")

            self._partition = partition
            self._buffer.append(line)
            self._buffer_bytes += len(line)
            if self._oldest_at is None:
                self._oldest_at = ts

            if self._on_buffer_size is not None:
                self._on_buffer_size(len(self._buffer))

            if self._should_flush():
                await self._flush_locked(reason="threshold")

    def _should_flush(self) -> bool:
        if not self._buffer:
            return False
        if len(self._buffer) >= self.max_records:
            return True
        if self._buffer_bytes >= self.max_bytes:
            return True
        if self._oldest_at is not None and (self._clock() - self._oldest_at) >= self.max_age_s:
            return True
        return False

    async def add_many(self, records: Iterable[Any], *, fetched_at: float | None = None) -> None:
        for record in records:
            await self.add(record, fetched_at=fetched_at)

    async def maybe_flush(self) -> bool:
        """Schreibt, wenn eine Grenze erreicht ist. Fuer den Leerlauf gedacht:
        ohne diesen Aufruf bliebe ein halbvoller Puffer bei einer stillen
        Quelle beliebig lange liegen."""
        async with self._lock:
            if self._should_flush():
                await self._flush_locked(reason="idle")
                return True
        return False

    async def flush(self, *, reason: str = "explicit") -> int:
        async with self._lock:
            return await self._flush_locked(reason=reason)

    async def _flush_locked(self, *, reason: str) -> int:
        if not self._buffer:
            return 0
        payload = b"".join(self._buffer)
        count = len(self._buffer)
        partition = self._partition or self._partition_for(self._clock())
        first_ts = self._oldest_at or self._clock()
        key = self._object_key(partition, first_ts)

        body = gzip.compress(payload) if self.compress else payload
        content_type = "application/gzip" if self.compress else "application/x-ndjson"

        try:
            await self._store.put(key, body, content_type=content_type)
        except Exception as exc:  # noqa: BLE001 - jeder Speicherfehler fuehrt zum Spool
            logger.error(
                "Bronze-Schreibvorgang nach %s fehlgeschlagen (%s). Buendel wandert "
                "in den Spool und wird spaeter nachgereicht.", key, exc,
            )
            self._spool(key, body)
            self._reset_buffer()
            if self._on_flush is not None:
                self._on_flush("spooled")
            return count

        self.flushed_batches += 1
        self.flushed_records += count
        self._reset_buffer()
        if self._on_flush is not None:
            self._on_flush("ok")
        logger.info("Bronze: %d Saetze nach %s (%s, %d Bytes)", count, key, reason, len(body))
        return count

    def _reset_buffer(self) -> None:
        self._buffer.clear()
        self._buffer_bytes = 0
        self._oldest_at = None
        if self._on_buffer_size is not None:
            self._on_buffer_size(0)

    # -- Spool ------------------------------------------------------------

    def _spool(self, key: str, body: bytes) -> None:
        if self._spool_dir is None:
            logger.critical(
                "Kein Spool-Verzeichnis konfiguriert - %d Bytes Rohdaten gehen "
                "verloren. spool_dir setzen.", len(body),
            )
            return
        target = self._spool_dir / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        self.spooled_batches += 1

    async def drain_spool(self) -> int:
        """Reicht gespoolte Buendel nach. Gehoert in den Leerlauf des Runners."""
        if self._spool_dir is None or not self._spool_dir.exists():
            return 0
        delivered = 0
        for path in sorted(self._spool_dir.rglob("*.jsonl*")):
            if path.is_dir():
                continue
            key = str(path.relative_to(self._spool_dir))
            content_type = "application/gzip" if key.endswith(".gz") else "application/x-ndjson"
            try:
                await self._store.put(key, path.read_bytes(), content_type=content_type)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Spool-Buendel %s weiterhin nicht zustellbar: %s", key, exc)
                break  # Reihenfolge halten: beim ersten Fehler abbrechen
            path.unlink()
            delivered += 1
            self.flushed_batches += 1
            if self._on_flush is not None:
                self._on_flush("spool_recovered")
        if delivered:
            logger.info("%d gespoolte Bronze-Buendel nachgereicht", delivered)
        return delivered

    async def close(self) -> None:
        await self.flush(reason="shutdown")
        await self._store.close()
