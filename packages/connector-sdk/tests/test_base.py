"""Basisklasse: HTTP-Fehlerfaelle, Zeitstempel, Vertrag."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from prometheus_client import CollectorRegistry

from argus_connector.base import BaseConnector, ConnectorMode, FetchResult, HealthStatus, RawRecord
from argus_connector.config import ConnectorSettings
from argus_connector.metrics import ConnectorMetrics
from argus_connector.retry import ConnectorError, ErrorKind
from argus_connector.runner import build_cursor_store


def _connector(settings, handler) -> BaseConnector:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="http://quelle.invalid")
    metrics = ConnectorMetrics("c", "s", registry=CollectorRegistry())
    connector = BaseConnector(settings, metrics=metrics, client=client)
    connector.dedupe_fields = ("id",)
    return connector


class TestHttpErrorHandling:
    async def test_empty_response_is_classified(self, settings):
        connector = _connector(settings, lambda request: httpx.Response(200, content=b""))
        with pytest.raises(ConnectorError) as excinfo:
            await connector.get_json("/x")
        assert excinfo.value.kind is ErrorKind.EMPTY_RESPONSE
        assert excinfo.value.retryable, "eine leere Antwort kann beim naechsten Mal Daten haben"

    async def test_invalid_json_names_the_beginning_of_the_body(self, settings):
        """Die Fehlermeldung muss zeigen, was da kam - meist eine HTML-Fehlerseite."""
        body = b"<html><head><title>502 Bad Gateway</title></head>"
        connector = _connector(settings, lambda request: httpx.Response(200, content=body))
        with pytest.raises(ConnectorError) as excinfo:
            await connector.get_json("/x")
        assert excinfo.value.kind is ErrorKind.INVALID_PAYLOAD
        assert "502 Bad Gateway" in str(excinfo.value)

    async def test_invalid_json_is_not_retried(self, settings):
        """Ein kaputter Body wird beim naechsten Versuch genauso kaputt sein."""
        calls = 0

        def handler(request):
            nonlocal calls
            calls += 1
            return httpx.Response(200, content=b"{kein json")

        connector = _connector(settings, handler)
        with pytest.raises(ConnectorError):
            await connector.get_json("/x")
        assert calls == 1

    async def test_server_error_is_retried(self, settings):
        calls = 0

        def handler(request):
            nonlocal calls
            calls += 1
            if calls < 3:
                return httpx.Response(503)
            return httpx.Response(200, json={"ok": True})

        connector = _connector(settings, handler)
        assert await connector.get_json("/x") == {"ok": True}
        assert calls == 3

    async def test_client_error_is_not_retried(self, settings):
        calls = 0

        def handler(request):
            nonlocal calls
            calls += 1
            return httpx.Response(404)

        connector = _connector(settings, handler)
        with pytest.raises(httpx.HTTPStatusError):
            await connector.get_json("/x")
        assert calls == 1

    async def test_identifying_user_agent_is_sent(self, settings):
        """Kapitel 14: ein Betreiber muss erkennen koennen, wer abruft."""
        seen: list[str] = []

        def handler(request):
            seen.append(request.headers.get("User-Agent", ""))
            return httpx.Response(200, json={})

        metrics = ConnectorMetrics("c", "s", registry=CollectorRegistry())
        connector = BaseConnector(settings, metrics=metrics)
        connector._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://quelle.invalid",
            headers=connector.client.headers,
        )
        await connector.get_json("/x")
        assert seen[0].startswith("ARGUS/")
        assert settings.connector_id in seen[0]


class TestClockSkew:
    async def test_large_skew_is_reported(self, settings):
        """Eine Quelle, deren Uhr um Stunden falsch geht, macht jeden
        Zeitvergleich unbrauchbar - das muss auffallen."""
        far_future = datetime(2030, 1, 1, tzinfo=UTC)
        import email.utils

        def handler(request):
            return httpx.Response(
                200,
                json={"ok": True},
                headers={"Date": email.utils.format_datetime(far_future)},
            )

        connector = _connector(settings, handler)
        await connector.get_json("/x")
        assert connector.last_clock_skew_s is not None
        assert connector.last_clock_skew_s > 60 * 60 * 24

    async def test_missing_date_header_is_not_an_error(self, settings):
        connector = _connector(settings, lambda request: httpx.Response(200, json={"ok": True}))
        await connector.get_json("/x")
        assert connector.last_clock_skew_s is None


class TestTimestampParsing:
    # Aus dem Datum berechnet statt eingetippt - eine falsch abgeschriebene
    # Epochenzahl testet nichts ausser der eigenen Kopie.
    REFERENCE = datetime(2026, 8, 28, 9, 14, 3, tzinfo=UTC).timestamp()

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("2026-08-28T09:14:03Z", REFERENCE),
            ("2026-08-28T09:14:03+00:00", REFERENCE),
            (REFERENCE, REFERENCE),
            (REFERENCE + 0.5, REFERENCE + 0.5),
            # Millisekunden werden erkannt.
            (REFERENCE * 1000, REFERENCE),
            (None, None),
            ("kein zeitstempel", None),
        ],
    )
    def test_to_epoch(self, value, expected):
        result = BaseConnector.to_epoch(value)
        if expected is None:
            assert result is None
        else:
            assert result == pytest.approx(expected, abs=1)

    def test_to_iso_round_trip(self):
        assert BaseConnector.to_iso("2026-08-28T09:14:03Z") == "2026-08-28T09:14:03Z"

    def test_to_iso_accepts_epoch_and_milliseconds(self):
        """Quellen liefern Zeit in jedem denkbaren Format - hier wird daraus
        genau eine Schreibweise."""
        assert BaseConnector.to_iso(self.REFERENCE) == "2026-08-28T09:14:03Z"
        assert BaseConnector.to_iso(self.REFERENCE * 1000) == "2026-08-28T09:14:03Z"

    def test_to_iso_passes_none_through(self):
        assert BaseConnector.to_iso(None) is None
        assert BaseConnector.to_iso("kein zeitstempel") is None

    def test_naive_datetime_is_treated_as_utc(self):
        """ARGUS rechnet in UTC. Ein Zeitstempel ohne Zone ist UTC, nicht
        Ortszeit - alles andere waere eine stille Verschiebung."""
        # Absichtlich ohne Zeitzone: genau dieser Fall wird geprueft.
        naive = datetime(2026, 8, 28, 9, 14, 3)  # noqa: DTZ001
        aware = datetime(2026, 8, 28, 9, 14, 3, tzinfo=UTC)
        assert BaseConnector.to_epoch(naive) == BaseConnector.to_epoch(aware)


class TestContract:
    async def test_default_health_is_ok(self, settings):
        metrics = ConnectorMetrics("c", "s", registry=CollectorRegistry())
        status = await BaseConnector(settings, metrics=metrics).health()
        assert status.healthy

    def test_health_status_helpers(self):
        assert HealthStatus.ok("laeuft").healthy
        assert not HealthStatus.failing("weg").healthy

    async def test_fetch_and_normalize_must_be_implemented(self, settings):
        metrics = ConnectorMetrics("c", "s", registry=CollectorRegistry())
        connector = BaseConnector(settings, metrics=metrics)
        with pytest.raises(NotImplementedError):
            await connector.fetch(None)
        with pytest.raises(NotImplementedError):
            connector.normalize(RawRecord(payload={}))

    async def test_backfill_says_so_when_unsupported(self, settings):
        """Die Meldung muss den Ausweg nennen, nicht nur das Problem."""
        metrics = ConnectorMetrics("c", "s", registry=CollectorRegistry())
        connector = BaseConnector(settings, metrics=metrics)
        with pytest.raises(NotImplementedError, match="Bronze-Layer"):
            async for _ in connector.backfill(datetime.now(UTC), datetime.now(UTC)):
                pass

    def test_dedupe_key_requires_configured_fields(self, settings):
        metrics = ConnectorMetrics("c", "s", registry=CollectorRegistry())
        connector = BaseConnector(settings, metrics=metrics)
        with pytest.raises(RuntimeError, match="dedupe_fields"):
            connector.dedupe_key_for({"id": 1})

    def test_fetch_result_length(self):
        assert len(FetchResult(records=[RawRecord(payload={})] * 3)) == 3

    def test_modes(self):
        assert ConnectorMode.POLL.value == "poll"


class TestCursorStoreFactory:
    def test_memory_backend(self):
        settings = ConnectorSettings(cursor={"backend": "memory"})
        from argus_connector.cursor import MemoryCursorStore

        assert isinstance(build_cursor_store(settings), MemoryCursorStore)

    def test_chained_without_dsn_is_refused(self):
        """Ohne dauerhafte Schicht bedeutet ein geleerter Cache einen Neulauf -
        das darf nicht stillschweigend passieren."""
        settings = ConnectorSettings(cursor={"backend": "chained", "postgres_dsn": None})
        with pytest.raises(ConnectorError, match="dauerhafte"):
            build_cursor_store(settings)

    def test_postgres_without_dsn_is_refused(self):
        settings = ConnectorSettings(cursor={"backend": "postgres", "postgres_dsn": None})
        with pytest.raises(ConnectorError, match="POSTGRES_DSN"):
            build_cursor_store(settings)

    def test_chained_with_dsn(self):
        from argus_connector.cursor import ChainedCursorStore

        settings = ConnectorSettings(
            cursor={"backend": "chained", "postgres_dsn": "postgresql://x/y"}
        )
        assert isinstance(build_cursor_store(settings), ChainedCursorStore)


class TestSettingsFromEnvironment:
    def test_nested_environment_variables(self, monkeypatch):
        monkeypatch.setenv("ARGUS_CONNECTOR_ID", "ingest-sea")
        monkeypatch.setenv("ARGUS_NATS__URL", "nats://bus:4222")
        monkeypatch.setenv("ARGUS_RATELIMIT__REQUESTS_PER_SECOND", "2.5")
        settings = ConnectorSettings()
        assert settings.connector_id == "ingest-sea"
        assert settings.nats.url == "nats://bus:4222"
        assert settings.ratelimit.requests_per_second == 2.5

    def test_invalid_backoff_factor_is_refused(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ConnectorSettings(ratelimit={"backoff_factor": 1.5})
