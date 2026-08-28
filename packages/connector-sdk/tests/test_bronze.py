"""Bronze-Archivierung: puffern, buendeln, nichts verlieren."""

from __future__ import annotations

import gzip
import json

import pytest

from argus_connector.bronze import BronzeWriter, FilesystemObjectStore


class RecordingStore:
    """Objektspeicher, der mitschreibt und auf Wunsch ausfaellt."""

    def __init__(self, *, fail_times: int = 0) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_times = fail_times
        self.attempts = 0

    async def put(self, key: str, body: bytes, *, content_type: str) -> None:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise OSError("Objektspeicher (simuliert) nicht erreichbar")
        self.objects[key] = body

    async def close(self) -> None:
        return None

    def lines(self, key: str) -> list[dict]:
        body = self.objects[key]
        if key.endswith(".gz"):
            body = gzip.decompress(body)
        return [json.loads(line) for line in body.splitlines() if line]


@pytest.fixture()
def store() -> RecordingStore:
    return RecordingStore()


def _writer(store, clock, tmp_path, **kwargs) -> BronzeWriter:
    defaults = dict(
        source_id="testquelle",
        max_records=1000,
        max_bytes=10 * 1024 * 1024,
        max_age_s=3600.0,
        compress=False,
        spool_dir=tmp_path / "spool",
        clock=clock,
    )
    defaults.update(kwargs)
    return BronzeWriter(store, **defaults)


class TestBuffering:
    async def test_single_record_is_not_written_immediately(self, store, clock, tmp_path):
        """Der ganze Sinn der Buendelung: nicht ein Objekt je Nachricht."""
        writer = _writer(store, clock, tmp_path)
        await writer.add({"a": 1})
        assert store.objects == {}
        assert writer.buffered_records == 1

    async def test_flush_on_record_count(self, store, clock, tmp_path):
        writer = _writer(store, clock, tmp_path, max_records=3)
        for i in range(3):
            await writer.add({"i": i})
        assert len(store.objects) == 1
        assert writer.buffered_records == 0

    async def test_flush_on_byte_size(self, store, clock, tmp_path):
        writer = _writer(store, clock, tmp_path, max_bytes=100)
        await writer.add({"payload": "x" * 200})
        assert len(store.objects) == 1

    async def test_flush_on_age(self, store, clock, tmp_path):
        writer = _writer(store, clock, tmp_path, max_age_s=60.0)
        await writer.add({"a": 1})
        assert not store.objects
        clock.advance(61)
        assert await writer.maybe_flush()
        assert len(store.objects) == 1

    async def test_thousand_records_become_one_object(self, store, clock, tmp_path):
        """Das Ziel aus der Aufgabenstellung, geprueft."""
        writer = _writer(store, clock, tmp_path, max_records=100_000)
        for i in range(1000):
            await writer.add({"i": i})
        await writer.flush()
        assert len(store.objects) == 1
        key = next(iter(store.objects))
        assert len(store.lines(key)) == 1000

    async def test_content_is_unchanged(self, store, clock, tmp_path):
        """Bronze ist die Rohantwort - unveraendert, Prinzip 1."""
        writer = _writer(store, clock, tmp_path)
        records = [{"a": 1, "nested": {"b": [1, 2]}}, {"a": 2, "text": "Grüße"}]
        for record in records:
            await writer.add(record)
        await writer.flush()
        assert store.lines(next(iter(store.objects))) == records


class TestPartitioning:
    async def test_key_follows_source_year_month_day_hour(self, store, clock, tmp_path):
        from datetime import UTC, datetime

        moment = datetime(2026, 8, 28, 9, 14, 3, tzinfo=UTC).timestamp()
        writer = _writer(store, clock, tmp_path)
        await writer.add({"a": 1}, fetched_at=moment)
        await writer.flush()
        key = next(iter(store.objects))
        assert key.startswith("testquelle/2026/08/28/09/")

    async def test_hour_rollover_closes_the_bundle(self, store, clock, tmp_path):
        """Eine Datei darf nie zwei Partitionen enthalten."""
        from datetime import UTC, datetime

        first = datetime(2026, 8, 28, 9, 59, 0, tzinfo=UTC).timestamp()
        second = datetime(2026, 8, 28, 10, 0, 1, tzinfo=UTC).timestamp()
        writer = _writer(store, clock, tmp_path, max_records=10_000)
        await writer.add({"a": 1}, fetched_at=first)
        await writer.add({"a": 2}, fetched_at=second)
        assert len(store.objects) == 1, "die alte Stunde wurde geschrieben"
        await writer.flush()
        assert len(store.objects) == 2
        hours = sorted(k.split("/")[4] for k in store.objects)
        assert hours == ["09", "10"]

    async def test_keys_are_unique_across_writers(self, store, clock, tmp_path):
        """Zwei Prozesse derselben Quelle duerfen einander nicht ueberschreiben."""
        from datetime import UTC, datetime

        moment = datetime(2026, 8, 28, 9, 14, 3, tzinfo=UTC).timestamp()
        for _ in range(2):
            writer = _writer(store, clock, tmp_path)
            await writer.add({"a": 1}, fetched_at=moment)
            await writer.flush()
        assert len(store.objects) == 2


class TestCompression:
    async def test_gzip_is_used_and_readable(self, store, clock, tmp_path):
        writer = _writer(store, clock, tmp_path, compress=True)
        await writer.add({"a": "x" * 500})
        await writer.flush()
        key = next(iter(store.objects))
        assert key.endswith(".jsonl.gz")
        assert store.lines(key) == [{"a": "x" * 500}]

    async def test_compression_actually_shrinks(self, store, clock, tmp_path):
        writer = _writer(store, clock, tmp_path, compress=True)
        for i in range(200):
            await writer.add({"gleichfoermig": "wiederholung", "i": i})
        await writer.flush()
        body = store.objects[next(iter(store.objects))]
        assert len(body) < len(gzip.decompress(body)) / 3


class TestFailureHandling:
    async def test_unreachable_store_spools_instead_of_losing(self, clock, tmp_path):
        """S3 nicht erreichbar: Bronze darf nie verloren gehen."""
        store = RecordingStore(fail_times=1)
        writer = _writer(store, clock, tmp_path)
        await writer.add({"a": 1})
        await writer.flush()
        assert store.objects == {}
        assert writer.spooled_batches == 1
        spooled = list((tmp_path / "spool").rglob("*.jsonl"))
        assert len(spooled) == 1

    async def test_spool_is_delivered_later(self, clock, tmp_path):
        store = RecordingStore(fail_times=1)
        writer = _writer(store, clock, tmp_path)
        await writer.add({"a": 1})
        await writer.flush()
        delivered = await writer.drain_spool()
        assert delivered == 1
        assert len(store.objects) == 1
        assert not list((tmp_path / "spool").rglob("*.jsonl"))

    async def test_spool_delivery_stops_at_the_first_failure(self, clock, tmp_path):
        """Die Reihenfolge der Buendel bleibt erhalten."""
        store = RecordingStore(fail_times=10)
        writer = _writer(store, clock, tmp_path)
        for i in range(3):
            await writer.add({"i": i})
            await writer.flush()
        assert writer.spooled_batches == 3
        assert await writer.drain_spool() == 0

    async def test_buffer_is_cleared_after_spooling(self, clock, tmp_path):
        """Sonst wuerde derselbe Satz beim naechsten Flush erneut gespoolt."""
        store = RecordingStore(fail_times=1)
        writer = _writer(store, clock, tmp_path)
        await writer.add({"a": 1})
        await writer.flush()
        assert writer.buffered_records == 0

    async def test_close_writes_the_remaining_buffer(self, store, clock, tmp_path):
        """SIGTERM mitten im Batch: der Puffer muss auf die Platte."""
        writer = _writer(store, clock, tmp_path)
        for i in range(7):
            await writer.add({"i": i})
        await writer.close()
        assert len(store.objects) == 1
        assert len(store.lines(next(iter(store.objects)))) == 7

    async def test_flush_of_empty_buffer_does_nothing(self, store, clock, tmp_path):
        writer = _writer(store, clock, tmp_path)
        assert await writer.flush() == 0
        assert store.objects == {}


class TestFilesystemStore:
    async def test_writes_the_same_key_structure(self, tmp_path, clock):
        from datetime import UTC, datetime

        moment = datetime(2026, 8, 28, 9, 14, 3, tzinfo=UTC).timestamp()
        store = FilesystemObjectStore(tmp_path / "bronze")
        writer = _writer(store, clock, tmp_path, compress=False)
        await writer.add({"a": 1}, fetched_at=moment)
        await writer.flush()
        written = list((tmp_path / "bronze").rglob("*.jsonl"))
        assert len(written) == 1
        assert "testquelle/2026/08/28/09" in str(written[0])

    async def test_no_partial_files_remain(self, tmp_path, clock):
        store = FilesystemObjectStore(tmp_path / "bronze")
        writer = _writer(store, clock, tmp_path)
        await writer.add({"a": 1})
        await writer.flush()
        assert not list((tmp_path / "bronze").rglob("*.part"))


class TestCallbacks:
    async def test_flush_callback_reports_result(self, store, clock, tmp_path):
        results: list[str] = []
        writer = _writer(store, clock, tmp_path, on_flush=results.append)
        await writer.add({"a": 1})
        await writer.flush()
        assert results == ["ok"]

    async def test_buffer_callback_tracks_size(self, store, clock, tmp_path):
        sizes: list[int] = []
        writer = _writer(store, clock, tmp_path, on_buffer_size=sizes.append)
        await writer.add({"a": 1})
        await writer.add({"a": 2})
        await writer.flush()
        assert sizes[:2] == [1, 2]
        assert sizes[-1] == 0
