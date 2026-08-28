"""Cursor-Persistenz und das Zwei-Phasen-Muster.

Der Kern der Zusicherung "kein stiller Datenverlust". Die Speichertests laufen
gegen echte Dienste - ob ein Wert einen Prozessabsturz ueberlebt, zeigt kein
Mock.
"""

from __future__ import annotations

import uuid

import pytest

from argus_connector.cursor import (
    ChainedCursorStore,
    Cursor,
    CursorManager,
    MemoryCursorStore,
    PostgresCursorStore,
    ValkeyCursorStore,
)
from conftest import requires_postgres, requires_valkey


class TestCursorSerialisation:
    def test_round_trip(self):
        cursor = Cursor("c1", {"page": 7, "token": "abc"}, sequence=3)
        restored = Cursor.from_json(cursor.to_json())
        assert restored.connector_id == "c1"
        assert restored.value == {"page": 7, "token": "abc"}
        assert restored.sequence == 3

    def test_scalar_values(self):
        for value in (42, "token", None, [1, 2], {"a": 1}):
            assert Cursor.from_json(Cursor("c", value).to_json()).value == value


class _StoreContract:
    """Derselbe Vertrag fuer jede Umsetzung - sonst verhalten sie sich
    unterschiedlich und der Wechsel des Backends aendert die Semantik."""

    async def test_empty_store_returns_none(self, store):
        assert await store.load("unbekannt") is None
        assert await store.load_pending("unbekannt") is None

    async def test_save_and_load(self, store, connector_id):
        await store.save(Cursor(connector_id, {"page": 3}, sequence=1))
        loaded = await store.load(connector_id)
        assert loaded is not None
        assert loaded.value == {"page": 3}
        assert loaded.sequence == 1

    async def test_overwrite(self, store, connector_id):
        await store.save(Cursor(connector_id, 1, sequence=1))
        await store.save(Cursor(connector_id, 2, sequence=2))
        loaded = await store.load(connector_id)
        assert loaded.value == 2 and loaded.sequence == 2

    async def test_pending_is_separate_from_committed(self, store, connector_id):
        await store.save(Cursor(connector_id, "committed", sequence=1))
        await store.save_pending(Cursor(connector_id, "pending", sequence=2))
        assert (await store.load(connector_id)).value == "committed"
        assert (await store.load_pending(connector_id)).value == "pending"

    async def test_clear_pending_keeps_committed(self, store, connector_id):
        await store.save(Cursor(connector_id, "committed"))
        await store.save_pending(Cursor(connector_id, "pending"))
        await store.clear_pending(connector_id)
        assert await store.load_pending(connector_id) is None
        assert (await store.load(connector_id)).value == "committed"

    async def test_connectors_are_isolated(self, store, connector_id):
        other = f"{connector_id}-other"
        await store.save(Cursor(connector_id, "a"))
        await store.save(Cursor(other, "b"))
        assert (await store.load(connector_id)).value == "a"
        assert (await store.load(other)).value == "b"


class TestMemoryStore(_StoreContract):
    @pytest.fixture()
    def connector_id(self) -> str:
        return "mem-connector"

    @pytest.fixture()
    async def store(self):
        store = MemoryCursorStore()
        yield store
        await store.close()


@requires_valkey
class TestValkeyStore(_StoreContract):
    @pytest.fixture()
    def connector_id(self) -> str:
        return f"valkey-{uuid.uuid4().hex[:8]}"

    @pytest.fixture()
    async def store(self, valkey_url):
        store = ValkeyCursorStore(valkey_url, key_prefix="argus:test:cursor")
        yield store
        await store.close()

    async def test_survives_a_new_client(self, valkey_url, connector_id):
        """Der eigentliche Zweck: der Wert ueberlebt den Prozess."""
        first = ValkeyCursorStore(valkey_url, key_prefix="argus:test:cursor")
        await first.save(Cursor(connector_id, {"page": 99}, sequence=5))
        await first.close()

        second = ValkeyCursorStore(valkey_url, key_prefix="argus:test:cursor")
        loaded = await second.load(connector_id)
        await second.close()
        assert loaded is not None and loaded.value == {"page": 99}

    async def test_no_expiry_is_set(self, valkey_url, connector_id):
        """Ein verfallener Cursor bedeutet stillen Datenverlust oder einen
        vollstaendigen Neulauf. Beides ist inakzeptabel."""
        import redis.asyncio as redis

        store = ValkeyCursorStore(valkey_url, key_prefix="argus:test:cursor")
        await store.save(Cursor(connector_id, 1))
        client = redis.from_url(valkey_url, decode_responses=True)
        ttl = await client.ttl(f"argus:test:cursor:{connector_id}")
        await client.aclose()
        await store.close()
        assert ttl == -1, "der Cursor darf keine Ablaufzeit haben"


@requires_postgres
class TestPostgresStore(_StoreContract):
    @pytest.fixture()
    def connector_id(self) -> str:
        return f"pg-{uuid.uuid4().hex[:8]}"

    @pytest.fixture()
    async def store(self, postgres_dsn):
        store = PostgresCursorStore(postgres_dsn, schema="argus_connector_test")
        yield store
        await store.close()

    async def test_survives_a_new_connection(self, postgres_dsn, connector_id):
        first = PostgresCursorStore(postgres_dsn, schema="argus_connector_test")
        await first.save(Cursor(connector_id, {"page": 12}, sequence=4))
        await first.close()

        second = PostgresCursorStore(postgres_dsn, schema="argus_connector_test")
        loaded = await second.load(connector_id)
        await second.close()
        assert loaded is not None and loaded.sequence == 4


@requires_postgres
@requires_valkey
class TestChainedStore:
    @pytest.fixture()
    async def chained(self, valkey_url, postgres_dsn):
        fast = ValkeyCursorStore(valkey_url, key_prefix="argus:test:chain")
        durable = PostgresCursorStore(postgres_dsn, schema="argus_connector_test")
        store = ChainedCursorStore(fast, durable)
        yield store, fast, durable
        await store.close()

    async def test_writes_reach_both_layers(self, chained):
        store, fast, durable = chained
        connector_id = f"chain-{uuid.uuid4().hex[:8]}"
        await store.save(Cursor(connector_id, "wert", sequence=1))
        assert (await fast.load(connector_id)).value == "wert"
        assert (await durable.load(connector_id)).value == "wert"

    async def test_falls_back_to_durable_when_cache_is_empty(self, chained):
        """Ein geleerter Cache darf nie bedeuten, dass ein Konnektor von vorn
        anfaengt."""
        store, fast, durable = chained
        connector_id = f"chain-{uuid.uuid4().hex[:8]}"
        await durable.save(Cursor(connector_id, "nur-dauerhaft", sequence=9))
        loaded = await store.load(connector_id)
        assert loaded is not None and loaded.value == "nur-dauerhaft"

    async def test_survives_an_unreachable_cache(self, postgres_dsn):
        """Faellt Valkey aus, laeuft der Konnektor weiter - langsamer, aber
        korrekt."""
        broken = ValkeyCursorStore("redis://127.0.0.1:1/0")
        durable = PostgresCursorStore(postgres_dsn, schema="argus_connector_test")
        store = ChainedCursorStore(broken, durable)
        connector_id = f"chain-{uuid.uuid4().hex[:8]}"
        await store.save(Cursor(connector_id, "trotzdem"))
        loaded = await store.load(connector_id)
        assert loaded is not None and loaded.value == "trotzdem"


class TestCursorManager:
    """Das Zwei-Phasen-Muster."""

    @pytest.fixture()
    def manager(self):
        return CursorManager(MemoryCursorStore(), "c1")

    async def test_first_run_has_no_cursor(self, manager):
        assert await manager.restore() is None

    async def test_commit_advances_the_cursor(self, manager):
        await manager.restore()
        await manager.begin({"page": 1})
        committed = await manager.commit()
        assert committed.value == {"page": 1}
        assert committed.sequence == 1

    async def test_sequence_increases_per_batch(self, manager):
        await manager.restore()
        for expected in (1, 2, 3):
            await manager.begin(expected)
            assert (await manager.commit()).sequence == expected

    async def test_pending_is_written_before_commit(self):
        """Die Absicht steht fest, bevor irgendetwas veroeffentlicht wird."""
        store = MemoryCursorStore()
        manager = CursorManager(store, "c1")
        await manager.restore()
        await manager.begin({"page": 5})
        assert (await store.load_pending("c1")).value == {"page": 5}
        assert await store.load("c1") is None, "noch nichts festgeschrieben"

    async def test_crash_before_commit_resumes_from_the_last_commit(self):
        """Der entscheidende Fall: ein Absturz zwischen begin und commit darf
        den Cursor NICHT vorruecken - sonst waeren die Daten des Batches
        verloren."""
        store = MemoryCursorStore()
        first = CursorManager(store, "c1")
        await first.restore()
        await first.begin("batch-1")
        await first.commit()
        await first.begin("batch-2")
        # hier stirbt der Prozess

        second = CursorManager(store, "c1")
        resumed = await second.restore()
        assert resumed.value == "batch-1", "Wiederaufnahme ab dem letzten Commit"
        assert second.recovered_interrupted is True

    async def test_interrupted_pending_is_cleared_on_restore(self):
        store = MemoryCursorStore()
        first = CursorManager(store, "c1")
        await first.restore()
        await first.begin("x")

        second = CursorManager(store, "c1")
        await second.restore()
        assert await store.load_pending("c1") is None

    async def test_interrupted_batches_are_counted(self):
        store = MemoryCursorStore()
        first = CursorManager(store, "c1")
        await first.restore()
        await first.begin("a")
        await first.commit()
        await first.begin("b")  # abgebrochen

        second = CursorManager(store, "c1")
        await second.restore()
        await second.begin("b")
        committed = await second.commit()
        assert committed.interrupted_batches == 1

    async def test_abort_leaves_the_cursor_untouched(self, manager):
        await manager.restore()
        await manager.begin("a")
        await manager.commit()
        await manager.begin("b")
        await manager.abort()
        assert manager.committed.value == "a"
        assert manager.pending is None

    async def test_commit_without_begin_is_a_programming_error(self, manager):
        await manager.restore()
        with pytest.raises(RuntimeError, match="ohne vorheriges begin"):
            await manager.commit()
