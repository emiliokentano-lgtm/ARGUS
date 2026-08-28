"""Cursor-Persistenz mit Zwei-Phasen-Muster.

Der Kern der Zusicherung "kein stiller Datenverlust bei Absturz".

Ablauf je Batch:

    1. begin(next_cursor)   -> 'pending' wird geschrieben
    2. Bronze schreiben
    3. Auf den Bus veroeffentlichen und Bestaetigung abwarten
    4. commit()             -> 'committed' = pending, pending geloescht

Stirbt der Prozess zwischen 1 und 4, steht beim Neustart 'committed' noch auf
dem alten Wert: der Batch wird wiederholt. Das kann Doppelzustellungen
erzeugen - die sind erlaubt und ueber den dedupe_key erkennbar. Was nicht
passieren darf, ist der umgekehrte Fall: ein fortgeschriebener Cursor fuer
Daten, die nie ankamen. Deshalb wird nach dem Publish festgeschrieben, nie
davor.

Das zusaetzlich gespeicherte 'pending' ist kein Wiederaufsetzpunkt, sondern
Diagnose: es sagt beim Neustart, welcher Batch unterbrochen wurde.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Cursor:
    """Wiederaufnahmepunkt einer Quelle.

    `value` ist bewusst freiform: eine Seitenzahl, ein Zeitstempel, ein Token,
    ein zusammengesetzter Zustand. Nur der Konnektor weiss, was er bedeutet.
    """

    connector_id: str
    value: Any
    sequence: int = 0
    updated_at: float = field(default_factory=time.time)
    # Zaehlt Batches, die begonnen, aber nie festgeschrieben wurden.
    interrupted_batches: int = 0

    def to_json(self) -> str:
        return json.dumps(
            {
                "connector_id": self.connector_id,
                "value": self.value,
                "sequence": self.sequence,
                "updated_at": self.updated_at,
                "interrupted_batches": self.interrupted_batches,
            },
            separators=(",", ":"),
            default=str,
        )

    @classmethod
    def from_json(cls, raw: str | bytes) -> Cursor:
        data = json.loads(raw)
        return cls(
            connector_id=data["connector_id"],
            value=data.get("value"),
            sequence=int(data.get("sequence", 0)),
            updated_at=float(data.get("updated_at", time.time())),
            interrupted_batches=int(data.get("interrupted_batches", 0)),
        )


@runtime_checkable
class CursorStore(Protocol):
    """Ablage fuer Cursor. Jede Umsetzung muss beide Schluessel fuehren."""

    async def load(self, connector_id: str) -> Cursor | None: ...
    async def load_pending(self, connector_id: str) -> Cursor | None: ...
    async def save(self, cursor: Cursor) -> None: ...
    async def save_pending(self, cursor: Cursor) -> None: ...
    async def clear_pending(self, connector_id: str) -> None: ...
    async def close(self) -> None: ...


class MemoryCursorStore:
    """Fuer Tests und fuer Konnektoren, die bewusst nicht wiederaufsetzen."""

    def __init__(self) -> None:
        self._committed: dict[str, str] = {}
        self._pending: dict[str, str] = {}

    async def load(self, connector_id: str) -> Cursor | None:
        raw = self._committed.get(connector_id)
        return Cursor.from_json(raw) if raw else None

    async def load_pending(self, connector_id: str) -> Cursor | None:
        raw = self._pending.get(connector_id)
        return Cursor.from_json(raw) if raw else None

    async def save(self, cursor: Cursor) -> None:
        self._committed[cursor.connector_id] = cursor.to_json()

    async def save_pending(self, cursor: Cursor) -> None:
        self._pending[cursor.connector_id] = cursor.to_json()

    async def clear_pending(self, connector_id: str) -> None:
        self._pending.pop(connector_id, None)

    async def close(self) -> None:
        return None


class ValkeyCursorStore:
    """Schnelle Ablage in Valkey/Redis.

    Bewusst ohne Ablaufzeit: ein verfallener Cursor bedeutet stillen
    Datenverlust oder einen vollstaendigen Neulauf. Valkey ist hier trotzdem
    nur die schnelle Schicht - die dauerhafte ist Postgres.
    """

    def __init__(self, url: str, *, key_prefix: str = "argus:cursor", client: Any = None) -> None:
        self._url = url
        self._prefix = key_prefix
        self._client = client

    async def _get_client(self) -> Any:
        if self._client is None:
            import redis.asyncio as redis  # lokal importiert: optionale Abhaengigkeit

            self._client = redis.from_url(self._url, decode_responses=True)
        return self._client

    def _key(self, connector_id: str, suffix: str = "") -> str:
        return f"{self._prefix}:{connector_id}{suffix}"

    async def load(self, connector_id: str) -> Cursor | None:
        client = await self._get_client()
        raw = await client.get(self._key(connector_id))
        return Cursor.from_json(raw) if raw else None

    async def load_pending(self, connector_id: str) -> Cursor | None:
        client = await self._get_client()
        raw = await client.get(self._key(connector_id, ":pending"))
        return Cursor.from_json(raw) if raw else None

    async def save(self, cursor: Cursor) -> None:
        client = await self._get_client()
        await client.set(self._key(cursor.connector_id), cursor.to_json())

    async def save_pending(self, cursor: Cursor) -> None:
        client = await self._get_client()
        await client.set(self._key(cursor.connector_id, ":pending"), cursor.to_json())

    async def clear_pending(self, connector_id: str) -> None:
        client = await self._get_client()
        await client.delete(self._key(connector_id, ":pending"))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class PostgresCursorStore:
    """Dauerhafte Ablage in PostgreSQL.

    Eigenes Schema (`argus_connector`), damit die Betriebszustaende der
    Konnektoren nicht im Domaenenschema liegen und getrennt gesichert werden
    koennen.
    """

    def __init__(self, dsn: str, *, schema: str = "argus_connector", pool: Any = None) -> None:
        self._dsn = dsn
        self._schema = schema
        self._pool = pool
        self._ready = False

    async def _connect(self) -> Any:
        import psycopg

        return await psycopg.AsyncConnection.connect(self._dsn, autocommit=True)

    async def _ensure_table(self) -> None:
        if self._ready:
            return
        async with await self._connect() as conn:
            await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{self._schema}"')
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS "{self._schema}".cursors (
                    connector_id text NOT NULL,
                    slot         text NOT NULL,
                    payload      jsonb NOT NULL,
                    updated_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
                    PRIMARY KEY (connector_id, slot)
                )
                """
            )
            await conn.execute(
                f'COMMENT ON TABLE "{self._schema}".cursors IS '
                "'Wiederaufnahmepunkte der Konnektoren. slot = committed | pending.'"
            )
        self._ready = True

    async def _read(self, connector_id: str, slot: str) -> Cursor | None:
        await self._ensure_table()
        async with await self._connect() as conn:
            cur = await conn.execute(
                # Unterdrueckung unten begruendet: der Schemaname kommt aus der
                # Konfiguration des Prozesses, nie aus einer Nachricht
                # oder Nutzereingabe. Werte werden ausschliesslich als
                # Parameter uebergeben.
                f'SELECT payload FROM "{self._schema}".cursors '  # noqa: S608
                "WHERE connector_id = %s AND slot = %s",
                (connector_id, slot),
            )
            row = await cur.fetchone()
        if not row:
            return None
        payload = row[0]
        return Cursor.from_json(payload if isinstance(payload, str) else json.dumps(payload))

    async def _write(self, cursor: Cursor, slot: str) -> None:
        await self._ensure_table()
        async with await self._connect() as conn:
            await conn.execute(
                f'INSERT INTO "{self._schema}".cursors (connector_id, slot, payload) '  # noqa: S608
                "VALUES (%s, %s, %s::jsonb) "
                "ON CONFLICT (connector_id, slot) DO UPDATE "
                "SET payload = excluded.payload, updated_at = clock_timestamp()",
                (cursor.connector_id, slot, cursor.to_json()),
            )

    async def load(self, connector_id: str) -> Cursor | None:
        return await self._read(connector_id, "committed")

    async def load_pending(self, connector_id: str) -> Cursor | None:
        return await self._read(connector_id, "pending")

    async def save(self, cursor: Cursor) -> None:
        await self._write(cursor, "committed")

    async def save_pending(self, cursor: Cursor) -> None:
        await self._write(cursor, "pending")

    async def clear_pending(self, connector_id: str) -> None:
        await self._ensure_table()
        async with await self._connect() as conn:
            await conn.execute(
                f'DELETE FROM "{self._schema}".cursors '  # noqa: S608
                "WHERE connector_id = %s AND slot = 'pending'",
                (connector_id,),
            )

    async def close(self) -> None:
        return None


class ChainedCursorStore:
    """Valkey als schnelle, Postgres als dauerhafte Schicht.

    Lesen: bevorzugt aus dem schnellen Speicher. Ist er leer - Neustart des
    Caches, Verdraengung, frisch aufgesetzte Umgebung -, kommt der Wert aus der
    dauerhaften Schicht. Ein leerer Cache darf nie bedeuten, dass ein Konnektor
    von vorn anfaengt.

    Schreiben: **zuerst dauerhaft**, dann schnell. Andersherum koennte ein
    Absturz zwischen beiden Schritten einen Cursor hinterlassen, der nur im
    fluechtigen Speicher steht.
    """

    def __init__(self, fast: CursorStore, durable: CursorStore) -> None:
        self._fast = fast
        self._durable = durable

    async def _load_from(self, method: str, connector_id: str) -> Cursor | None:
        try:
            cursor: Cursor | None = await getattr(self._fast, method)(connector_id)
            if cursor is not None:
                return cursor
        except Exception as exc:  # noqa: BLE001 - der schnelle Speicher darf ausfallen
            logger.warning(
                "Schneller Cursor-Speicher nicht erreichbar (%s), weiche auf den "
                "dauerhaften aus: %s",
                method,
                exc,
            )
        fallback: Cursor | None = await getattr(self._durable, method)(connector_id)
        return fallback

    async def load(self, connector_id: str) -> Cursor | None:
        return await self._load_from("load", connector_id)

    async def load_pending(self, connector_id: str) -> Cursor | None:
        return await self._load_from("load_pending", connector_id)

    async def save(self, cursor: Cursor) -> None:
        await self._durable.save(cursor)
        try:
            await self._fast.save(cursor)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cursor konnte nicht in den schnellen Speicher: %s", exc)

    async def save_pending(self, cursor: Cursor) -> None:
        await self._durable.save_pending(cursor)
        try:
            await self._fast.save_pending(cursor)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Pending-Cursor konnte nicht in den schnellen Speicher: %s", exc)

    async def clear_pending(self, connector_id: str) -> None:
        await self._durable.clear_pending(connector_id)
        try:
            await self._fast.clear_pending(connector_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Pending-Cursor im schnellen Speicher nicht geloescht: %s", exc)

    async def close(self) -> None:
        await self._fast.close()
        await self._durable.close()


class CursorManager:
    """Fasst das Zwei-Phasen-Muster zusammen.

    Der Konnektor benutzt nur diese Klasse; die Reihenfolge der Schritte ist
    hier festgelegt und nicht in jedem Konnektor neu.
    """

    def __init__(self, store: CursorStore, connector_id: str) -> None:
        self._store = store
        self._connector_id = connector_id
        self._committed: Cursor | None = None
        self._pending: Cursor | None = None
        self.recovered_interrupted = False

    @property
    def committed(self) -> Cursor | None:
        return self._committed

    @property
    def pending(self) -> Cursor | None:
        return self._pending

    async def restore(self) -> Cursor | None:
        """Beim Start: der festgeschriebene Cursor ist der Wiederaufsetzpunkt.

        Ein vorhandener Pending-Cursor bedeutet, dass der letzte Batch
        unterbrochen wurde. Er wird protokolliert und verworfen - wiederholt
        wird ab dem festgeschriebenen Stand.
        """
        self._committed = await self._store.load(self._connector_id)
        pending = await self._store.load_pending(self._connector_id)
        if pending is not None:
            self.recovered_interrupted = True
            logger.warning(
                "Unterbrochener Batch gefunden (pending sequence=%s, committed sequence=%s). "
                "Wiederaufnahme ab dem festgeschriebenen Stand - Doppelzustellungen "
                "sind moeglich und ueber den dedupe_key erkennbar.",
                pending.sequence,
                self._committed.sequence if self._committed else 0,
            )
            await self._store.clear_pending(self._connector_id)
        return self._committed

    async def begin(self, value: Any) -> Cursor:
        """Phase 1: Absicht festhalten, bevor irgendetwas veroeffentlicht wird."""
        sequence = (self._committed.sequence if self._committed else 0) + 1
        interrupted = self._committed.interrupted_batches if self._committed else 0
        self._pending = Cursor(
            connector_id=self._connector_id,
            value=value,
            sequence=sequence,
            interrupted_batches=interrupted + (1 if self.recovered_interrupted else 0),
        )
        await self._store.save_pending(self._pending)
        return self._pending

    async def commit(self) -> Cursor:
        """Phase 2: nach erfolgreicher Zustellung festschreiben."""
        if self._pending is None:
            raise RuntimeError("commit() ohne vorheriges begin()")
        self._pending.updated_at = time.time()
        await self._store.save(self._pending)
        await self._store.clear_pending(self._connector_id)
        self._committed = self._pending
        self._pending = None
        self.recovered_interrupted = False
        return self._committed

    async def abort(self) -> None:
        """Batch aufgeben, ohne festzuschreiben. Der naechste Lauf wiederholt ihn."""
        if self._pending is None:
            return
        logger.info(
            "Batch aufgegeben, Cursor bleibt bei sequence=%s",
            self._committed.sequence if self._committed else 0,
        )
        await self._store.clear_pending(self._connector_id)
        self._pending = None
