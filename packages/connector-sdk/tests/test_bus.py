"""Veroeffentlichung auf dem Bus."""

from __future__ import annotations

import json

import pytest

from argus_connector.bus import BusUnavailable, MemoryPublisher, NatsPublisher, PublishResult


class TestMemoryPublisher:
    async def test_publishes(self):
        publisher = MemoryPublisher()
        await publisher.connect()
        assert await publisher.publish("s.a", {"x": 1}, dedupe_key="k1")
        assert publisher.messages == [("s.a", {"x": 1}, "k1")]

    async def test_duplicate_msg_id_is_not_republished(self):
        """Bildet das JetStream-Verhalten nach: gleiche Id im Dedupe-Fenster
        gilt als zugestellt, wird aber nicht erneut gespeichert."""
        publisher = MemoryPublisher()
        await publisher.connect()
        assert await publisher.publish("s", {"x": 1}, dedupe_key="k")
        assert not await publisher.publish("s", {"x": 1}, dedupe_key="k")
        assert len(publisher.messages) == 1
        assert publisher.duplicates == 1

    async def test_batch_counts_published_and_duplicates(self):
        publisher = MemoryPublisher()
        await publisher.connect()
        result = await publisher.publish_batch(
            [("s", {"i": 1}, "a"), ("s", {"i": 2}, "b"), ("s", {"i": 1}, "a")]
        )
        assert result == PublishResult(published=2, duplicates=1)
        assert result.total == 3

    async def test_failure_is_raised_as_bus_unavailable(self):
        publisher = MemoryPublisher(fail_after=2)
        await publisher.connect()
        with pytest.raises(BusUnavailable):
            await publisher.publish_batch(
                [("s", {}, "a"), ("s", {}, "b"), ("s", {}, "c")]
            )


class _FakeAck:
    def __init__(self, duplicate: bool = False) -> None:
        self.duplicate = duplicate


class _FakeJetStream:
    def __init__(self, *, duplicate_ids: set[str] | None = None, fail: bool = False) -> None:
        self.published: list[tuple[str, bytes, dict]] = []
        self._duplicate_ids = duplicate_ids or set()
        self._fail = fail

    async def publish(self, subject, body, *, timeout, headers, stream):  # noqa: ANN001
        if self._fail:
            raise TimeoutError("keine Bestaetigung")
        self.published.append((subject, body, headers))
        return _FakeAck(duplicate=headers.get("Nats-Msg-Id") in self._duplicate_ids)


class _FakeConnection:
    def __init__(self, js: _FakeJetStream) -> None:
        self._js = js
        self.drained = False

    def jetstream(self) -> _FakeJetStream:
        return self._js

    async def drain(self) -> None:
        self.drained = True


class TestNatsPublisher:
    async def test_dedupe_key_becomes_the_msg_id(self):
        """Der Mechanismus, der Wiederholungen nach einem Absturz auffaengt."""
        js = _FakeJetStream()
        publisher = NatsPublisher("nats://x", connection=_FakeConnection(js))
        await publisher.connect()
        await publisher.publish("argus.raw.test", {"a": 1}, dedupe_key="schluessel-1")
        _, body, headers = js.published[0]
        assert headers["Nats-Msg-Id"] == "schluessel-1"
        assert json.loads(body) == {"a": 1}

    async def test_duplicate_ack_is_counted_not_republished(self):
        js = _FakeJetStream(duplicate_ids={"k"})
        publisher = NatsPublisher("nats://x", connection=_FakeConnection(js))
        await publisher.connect()
        assert not await publisher.publish("s", {"a": 1}, dedupe_key="k")
        assert publisher.duplicates == 1

    async def test_missing_ack_raises_bus_unavailable(self):
        """Ohne Bestaetigung gilt die Nachricht als nicht zugestellt - und der
        Cursor darf nicht vorruecken."""
        publisher = NatsPublisher(
            "nats://x", connection=_FakeConnection(_FakeJetStream(fail=True))
        )
        await publisher.connect()
        with pytest.raises(BusUnavailable):
            await publisher.publish("s", {"a": 1}, dedupe_key="k")

    async def test_batch_result(self):
        js = _FakeJetStream(duplicate_ids={"b"})
        publisher = NatsPublisher("nats://x", connection=_FakeConnection(js))
        await publisher.connect()
        result = await publisher.publish_batch(
            [("s", {"i": 1}, "a"), ("s", {"i": 2}, "b"), ("s", {"i": 3}, "c")]
        )
        assert result.published == 2 and result.duplicates == 1

    async def test_close_drains(self):
        connection = _FakeConnection(_FakeJetStream())
        publisher = NatsPublisher("nats://x", connection=connection)
        await publisher.connect()
        await publisher.close()
        assert connection.drained

    async def test_unicode_survives(self):
        js = _FakeJetStream()
        publisher = NatsPublisher("nats://x", connection=_FakeConnection(js))
        await publisher.connect()
        await publisher.publish("s", {"ort": "Fudschaira", "text": "Grüße"}, dedupe_key="k")
        assert json.loads(js.published[0][1])["text"] == "Grüße"
