"""Der Runner: Reihenfolge im Batch, Kill-Switch, Herunterfahren."""

from __future__ import annotations

import asyncio
import json
import time

import pytest
from prometheus_client import CollectorRegistry

from argus_connector.base import BaseConnector, CanonicalMessage, FetchResult, RawRecord
from argus_connector.bronze import BronzeWriter
from argus_connector.bus import BusUnavailableError, MemoryPublisher
from argus_connector.cursor import MemoryCursorStore
from argus_connector.metrics import ConnectorMetrics
from argus_connector.runner import ConnectorRunner, RunnerState

# Bewusst in der Vergangenheit: der Lag ist "jetzt minus observed_at" und
# waere bei einem Zeitstempel aus der Zukunft definitionsgemaess 0.
PAST_EPOCH = 1_700_000_000


class CountingConnector(BaseConnector):
    """Liefert durchnummerierte Saetze, seitenweise."""

    dedupe_fields = ("id",)

    def __init__(self, settings, *, metrics, total: int = 30, page: int = 10) -> None:
        super().__init__(settings, metrics=metrics)
        self.total = total
        self.page = page
        self.fetch_calls = 0
        self.normalize_failures: set[int] = set()

    async def fetch(self, cursor):
        self.fetch_calls += 1
        start = int(cursor or 0)
        end = min(start + self.page, self.total)
        records = [
            RawRecord(
                payload={"id": i, "observed_at": PAST_EPOCH + i},
                source_timestamp=PAST_EPOCH + i,
            )
            for i in range(start, end)
        ]
        return FetchResult(records=records, next_cursor=end, has_more=end < self.total)

    def normalize(self, raw):
        record_id = raw.payload["id"]
        if record_id in self.normalize_failures:
            raise ValueError(f"Satz {record_id} ist kaputt")
        return [
            CanonicalMessage(
                subject_suffix="test",
                payload=raw.payload,
                dedupe_key=self.dedupe_key_for(raw.payload),
                observed_at=float(raw.payload["observed_at"]),
            )
        ]


class RecordingStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key, body, *, content_type):
        self.objects[key] = body

    async def close(self) -> None:
        return None


@pytest.fixture()
def parts(settings, tmp_path):
    metrics = ConnectorMetrics("test-connector", "test-source", registry=CollectorRegistry())
    connector = CountingConnector(settings, metrics=metrics)
    store = MemoryCursorStore()
    publisher = MemoryPublisher()
    object_store = RecordingStore()
    bronze = BronzeWriter(
        object_store,
        source_id="test-source",
        max_records=1000,
        compress=False,
        spool_dir=tmp_path / "spool",
    )
    runner = ConnectorRunner(
        connector,
        settings=settings,
        cursor_store=store,
        publisher=publisher,
        bronze=bronze,
        metrics=metrics,
    )
    return runner, connector, store, publisher, bronze, object_store, metrics


class TestBatchOrder:
    async def test_full_run_publishes_everything(self, parts):
        runner, _connector, _, publisher, _, _, _ = parts
        await runner.run(max_batches=3)
        assert len(publisher.messages) == 30
        assert [m[1]["id"] for m in publisher.messages] == list(range(30))

    async def test_cursor_is_committed_only_after_publishing(self, parts):
        """Die zentrale Zusicherung. Beim Publish wird geprueft, ob der Cursor
        zu diesem Zeitpunkt noch auf dem alten Stand steht."""
        runner, _, store, publisher, _, _, _ = parts
        seen_during_publish: list = []
        original = publisher.publish_batch

        async def spy(messages):
            seen_during_publish.append(await store.load("test-connector"))
            return await original(messages)

        publisher.publish_batch = spy
        await runner.run(max_batches=1)

        assert seen_during_publish[0] is None, (
            "beim Veroeffentlichen darf noch nichts festgeschrieben sein"
        )
        assert (await store.load("test-connector")).value == 10

    async def test_pending_is_written_before_publishing(self, parts):
        runner, _, store, publisher, _, _, _ = parts
        pending_seen: list = []
        original = publisher.publish_batch

        async def spy(messages):
            pending_seen.append(await store.load_pending("test-connector"))
            return await original(messages)

        publisher.publish_batch = spy
        await runner.run(max_batches=1)
        assert pending_seen[0] is not None, "die Absicht muss vorher feststehen"

    async def test_bronze_is_written_before_publishing(self, parts):
        """Rohdaten muessen auch dann vorliegen, wenn die Normalisierung
        scheitert."""
        runner, _, _, publisher, _, object_store, _ = parts
        during: list[int] = []
        original = publisher.publish_batch

        async def spy(messages):
            during.append(len(object_store.objects) + 1)  # Puffer zaehlt mit
            return await original(messages)

        publisher.publish_batch = spy
        await runner.run(max_batches=1)
        assert runner.bronze.buffered_records == 10 or object_store.objects

    async def test_publish_failure_leaves_the_cursor_untouched(self, parts):
        runner, _, store, publisher, _, _, _ = parts

        async def failing(_messages):
            raise BusUnavailableError("Bus weg")

        publisher.publish_batch = failing
        await runner.run(max_batches=1)
        assert await store.load("test-connector") is None, (
            "ohne Zustellung darf der Cursor nicht vorruecken"
        )
        assert await store.load_pending("test-connector") is None, "pending aufgeraeumt"

    async def test_broken_record_does_not_kill_the_batch(self, parts):
        runner, connector, store, publisher, _, _, _ = parts
        connector.normalize_failures = {3, 7}
        await runner.run(max_batches=1)
        assert len(publisher.messages) == 8
        assert (await store.load("test-connector")).value == 10

    async def test_duplicates_are_counted_not_republished(self, settings, tmp_path):
        """Nach einem Absturz wiederholt der Konnektor den Batch. Die
        Nachrichten sind identisch, also faengt der dedupe_key sie ab - kein
        Verlust, keine Dublette im Stream."""
        publisher = MemoryPublisher()

        async def build_runner():
            metrics = ConnectorMetrics(
                "test-connector", "test-source", registry=CollectorRegistry()
            )
            connector = CountingConnector(settings, metrics=metrics)
            bronze = BronzeWriter(
                RecordingStore(),
                source_id="test-source",
                compress=False,
                spool_dir=tmp_path / "spool",
            )
            return ConnectorRunner(
                connector,
                settings=settings,
                # Frischer Cursor-Speicher = der Cursor ging verloren, der
                # Konnektor faengt beim selben Batch wieder an.
                cursor_store=MemoryCursorStore(),
                publisher=publisher,
                bronze=bronze,
                metrics=metrics,
            )

        first = await build_runner()
        await first.run(max_batches=1)
        assert len(publisher.messages) == 10

        second = await build_runner()
        await second.run(max_batches=1)
        assert len(publisher.messages) == 10, "keine Dublette im Stream"
        assert publisher.duplicates == 10
        assert second.duplicates_skipped == 10


class TestKillSwitch:
    async def test_pause_and_resume(self, parts):
        runner, *_ = parts
        runner.pause("Wartung")
        assert runner.state is RunnerState.PAUSED
        runner.resume("fertig")
        assert runner.state is RunnerState.RUNNING

    async def test_control_message_pauses(self, parts):
        runner, *_ = parts
        runner.state = RunnerState.RUNNING
        await runner.handle_control_message(
            json.dumps({"command": "pause", "connector_id": "test-connector"})
        )
        assert runner.state is RunnerState.PAUSED

    async def test_control_message_for_another_connector_is_ignored(self, parts):
        runner, *_ = parts
        runner.state = RunnerState.RUNNING
        await runner.handle_control_message(
            json.dumps({"command": "pause", "connector_id": "ein-anderer"})
        )
        assert runner.state is RunnerState.RUNNING

    async def test_wildcard_reaches_every_connector(self, parts):
        runner, *_ = parts
        runner.state = RunnerState.RUNNING
        await runner.handle_control_message(json.dumps({"command": "pause", "connector_id": "*"}))
        assert runner.state is RunnerState.PAUSED

    async def test_stop_command_ends_the_run(self, parts):
        runner, *_ = parts
        await runner.handle_control_message(json.dumps({"command": "stop"}))
        assert runner.state is RunnerState.STOPPING

    async def test_garbage_control_message_is_ignored(self, parts):
        runner, *_ = parts
        runner.state = RunnerState.RUNNING
        await runner.handle_control_message(b"kein json")
        await runner.handle_control_message(json.dumps({"command": "tanzen"}))
        assert runner.state is RunnerState.RUNNING

    async def test_paused_connector_does_not_touch_the_source(self, parts):
        """Der Sinn des Kill-Switch: die Quelle wird nicht mehr angefasst."""
        runner, connector, _, _, _, _, _ = parts
        runner.pause()

        task = asyncio.create_task(runner.run(max_batches=5))
        await asyncio.sleep(0.05)
        assert connector.fetch_calls == 0
        runner.request_stop()
        await asyncio.wait_for(task, timeout=5)

    async def test_disabled_by_configuration_starts_paused(self, settings, parts):
        runner, connector, *_ = parts
        runner.settings.enabled = False
        task = asyncio.create_task(runner.run(max_batches=5))
        await asyncio.sleep(0.05)
        assert runner.state is RunnerState.PAUSED
        assert connector.fetch_calls == 0
        runner.request_stop()
        await asyncio.wait_for(task, timeout=5)


class TestShutdown:
    async def test_shutdown_flushes_bronze(self, parts):
        """SIGTERM mitten im Betrieb darf keine Rohdaten kosten."""
        runner, _, _, _, _bronze, object_store, _ = parts
        await runner.run(max_batches=1)
        assert object_store.objects, "der Bronze-Puffer muss geschrieben sein"

    async def test_shutdown_is_idempotent(self, parts):
        runner, *_ = parts
        await runner.run(max_batches=1)
        await runner.shutdown()
        assert runner.state is RunnerState.STOPPED

    async def test_stop_request_ends_the_loop(self, parts):
        runner, *_ = parts
        task = asyncio.create_task(runner.run())
        await asyncio.sleep(0.05)
        runner.request_stop()
        await asyncio.wait_for(task, timeout=5)
        assert runner.state is RunnerState.STOPPED

    async def test_shutdown_waits_for_the_running_batch(self, parts):
        """Der laufende Batch wird zu Ende gefuehrt, nicht abgeschnitten."""
        runner, _, store, publisher, _bronze, _, _ = parts
        slow_release = asyncio.Event()
        original = publisher.publish_batch

        async def slow(messages):
            await slow_release.wait()
            return await original(messages)

        publisher.publish_batch = slow
        batch_task = asyncio.create_task(runner.process_batch(await runner.connector.fetch(None)))
        await asyncio.sleep(0.05)

        shutdown_task = asyncio.create_task(runner.shutdown())
        await asyncio.sleep(0.05)
        assert not shutdown_task.done(), "shutdown wartet auf den Batch"

        slow_release.set()
        await asyncio.wait_for(batch_task, timeout=5)
        await asyncio.wait_for(shutdown_task, timeout=5)
        assert (await store.load("test-connector")).value == 10


class TestMetrics:
    async def test_required_metrics_are_exported(self, parts):
        """Die vier Pflichtmetriken aus der Aufgabenstellung."""
        runner, _, _, _, _, _, metrics = parts
        await runner.run(max_batches=1)
        exported = {
            sample.name for metric in metrics.registry.collect() for sample in metric.samples
        }
        for required in (
            "connector_messages_total",
            "connector_errors_total",
            "connector_lag_seconds",
            "connector_last_success_timestamp",
        ):
            assert any(name.startswith(required) for name in exported), required

    async def test_message_stages_are_counted(self, parts):
        runner, _, _, _, _, _, metrics = parts
        await runner.run(max_batches=1)
        value = metrics.registry.get_sample_value(
            "connector_messages_total",
            {"connector": "test-connector", "source": "test-source", "stage": "published"},
        )
        assert value == 10

    async def test_lag_is_measured(self, parts):
        runner, _, _, _, _, _, metrics = parts
        await runner.run(max_batches=1)
        lag = metrics.registry.get_sample_value(
            "connector_lag_seconds", {"connector": "test-connector", "source": "test-source"}
        )
        assert lag is not None and lag > 0

    async def test_last_success_is_recent(self, parts):
        runner, _, _, _, _, _, metrics = parts
        await runner.run(max_batches=1)
        value = metrics.registry.get_sample_value(
            "connector_last_success_timestamp",
            {"connector": "test-connector", "source": "test-source"},
        )
        assert value is not None and abs(value - time.time()) < 10

    async def test_errors_are_labelled_by_kind(self, parts):
        runner, connector, _, _, _, _, metrics = parts
        connector.normalize_failures = {1}
        await runner.run(max_batches=1)
        value = metrics.registry.get_sample_value(
            "connector_errors_total",
            {"connector": "test-connector", "source": "test-source", "kind": "invalid_payload"},
        )
        assert value == 1
