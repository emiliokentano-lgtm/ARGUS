"""Abnahmekriterium: bei HTTP 429 drosselt der Konnektor messbar und erholt sich.

Gegen einen echten HTTP-Server, nicht gegen einen Mock der httpx-Schicht: die
Drosselung soll auch dann greifen, wenn sie durch die ganze Kette laeuft -
Rate-Limiter, Retry, Circuit Breaker, Retry-After-Auswertung.
"""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
from fixtures.mock_source import MockSource
from prometheus_client import CollectorRegistry

from argus_connector.base import BaseConnector, CanonicalMessage, FetchResult, RawRecord
from argus_connector.metrics import ConnectorMetrics

pytestmark = pytest.mark.integration


class SimpleConnector(BaseConnector):
    dedupe_fields = ("id",)

    def __init__(self, settings, *, metrics, source_url: str) -> None:
        super().__init__(settings, metrics=metrics)
        self._url = source_url

    async def fetch(self, cursor):
        data = await self.get_json(
            f"{self._url}/records", params={"cursor": int(cursor or 0), "limit": 10}
        )
        return FetchResult(
            records=[RawRecord(payload=item) for item in data["records"]],
            next_cursor=data["next_cursor"],
            has_more=bool(data["has_more"]),
        )

    def normalize(self, raw):
        return [CanonicalMessage("t", raw.payload, self.dedupe_key_for(raw.payload))]


def _connector(settings, source_url: str, **overrides):
    settings = settings.model_copy(deep=True)
    settings.ratelimit.requests_per_second = overrides.get("rps", 20.0)
    settings.ratelimit.burst = overrides.get("burst", 20)
    settings.ratelimit.backoff_factor = 0.5
    settings.ratelimit.recovery_step = 0.5
    settings.ratelimit.recovery_interval_s = overrides.get("recovery_interval", 0.2)
    settings.ratelimit.min_requests_per_second = 0.5
    settings.retry.max_attempts = overrides.get("max_attempts", 6)
    settings.retry.base_delay_s = 0.01
    settings.retry.max_delay_s = 0.2
    metrics = ConnectorMetrics("throttle-test", "mock", registry=CollectorRegistry())
    return SimpleConnector(settings, metrics=metrics, source_url=source_url), metrics


async def test_rate_is_halved_on_each_429(settings):
    with MockSource(total=100) as source:
        connector, _ = _connector(settings, source.url)
        try:
            source.throttle_next(2)
            await connector.fetch(0)
            # Zwei Drosselungen: 20 -> 10 -> 5
            assert connector.rate_limiter.current_rate == pytest.approx(5.0)
            assert connector.rate_limiter.throttle_events == 2
        finally:
            await connector.close()


async def test_throttling_is_measurable_in_elapsed_time(settings):
    """Der Kern des Kriteriums: die Drosselung ist an der Uhr ablesbar."""
    with MockSource(total=200) as source:
        # Hohes Erholungsintervall: sonst holt sich die Rate waehrend der
        # Messung schon wieder hoch und der Effekt verschwindet im Rauschen.
        connector, _ = _connector(settings, source.url, rps=50.0, burst=1, recovery_interval=60.0)
        try:
            started = time.monotonic()
            for cursor in range(0, 50, 10):
                await connector.fetch(cursor)
            baseline = time.monotonic() - started

            source.throttle_next(4)
            await connector.fetch(0)  # loest die Drosselung aus
            assert connector.rate_limiter.current_rate <= 50.0 / 8

            throttled_start = time.monotonic()
            for cursor in range(0, 50, 10):
                await connector.fetch(cursor)
            throttled = time.monotonic() - throttled_start
        finally:
            await connector.close()

    assert connector.rate_limiter.current_rate < 50.0
    assert throttled > baseline * 2, (
        f"nach der Drosselung dauerten dieselben Abrufe {throttled:.3f} s statt "
        f"{baseline:.3f} s - der Unterschied ist zu klein, um die Drosselung zu belegen"
    )


async def test_retry_after_header_is_honoured(settings):
    """Die Quelle sagt, wann sie wieder kann - das schlaegt jeden berechneten
    Backoff."""
    with MockSource(total=50) as source:
        connector, _ = _connector(settings, source.url, rps=100.0, burst=100)
        try:
            source.throttle_next(1, retry_after="1")
            started = time.monotonic()
            await connector.fetch(0)
            elapsed = time.monotonic() - started
        finally:
            await connector.close()

    assert elapsed >= 1.0, f"Retry-After: 1 wurde nicht eingehalten (nur {elapsed:.3f} s gewartet)"


async def test_connector_recovers_after_throttling(settings):
    """Nach der Drosselung kehrt die Rate schrittweise zurueck - und der
    Konnektor liefert wieder Daten."""
    with MockSource(total=200) as source:
        connector, _ = _connector(settings, source.url, recovery_interval=0.05)
        try:
            source.throttle_next(2)
            await connector.fetch(0)
            throttled_rate = connector.rate_limiter.current_rate
            assert throttled_rate < 20.0

            for cursor in range(0, 100, 10):
                await asyncio.sleep(0.06)  # Erholungsintervall verstreichen lassen
                result = await connector.fetch(cursor)
                assert len(result.records) == 10, "die Quelle liefert wieder"

            assert connector.rate_limiter.current_rate > throttled_rate, (
                "die Rate muss sich erholen, sonst bleibt der Konnektor fuer immer langsam"
            )
        finally:
            await connector.close()


async def test_persistent_throttling_still_gives_up(settings):
    """Wenn die Quelle dauerhaft drosselt, endet der Versuch mit einem Fehler -
    statt endlos zu warten."""
    with MockSource(total=50) as source:
        connector, metrics = _connector(settings, source.url, max_attempts=3)
        try:
            source.throttle_next(100)
            with pytest.raises(httpx.HTTPStatusError) as excinfo:
                await connector.fetch(0)
            assert excinfo.value.response.status_code == 429
        finally:
            await connector.close()

    assert source.state.throttle_hits == 3, "genau max_attempts Versuche"
    value = metrics.registry.get_sample_value(
        "connector_errors_total",
        {"connector": "throttle-test", "source": "mock", "kind": "rate_limited"},
    )
    assert value and value >= 3


async def test_rate_limit_metrics_are_exported(settings):
    with MockSource(total=50) as source:
        connector, metrics = _connector(settings, source.url)
        try:
            source.throttle_next(1)
            await connector.fetch(0)
        finally:
            await connector.close()

    current = metrics.registry.get_sample_value(
        "connector_rate_limit_requests_per_second",
        {"connector": "throttle-test", "source": "mock"},
    )
    assert current == pytest.approx(10.0)
    delay = metrics.registry.get_sample_value(
        "connector_rate_limit_delay_seconds_total",
        {"connector": "throttle-test", "source": "mock"},
    )
    assert delay is not None


async def test_clock_skew_is_measured_from_the_date_header(settings):
    """Uhrendrift zwischen Quelle und System - der Date-Header genuegt fuer die
    Frage 'geht die Uhr der Quelle um Minuten falsch'."""
    with MockSource(total=10) as source:
        connector, metrics = _connector(settings, source.url)
        try:
            await connector.fetch(0)
        finally:
            await connector.close()

    assert connector.last_clock_skew_s is not None
    assert abs(connector.last_clock_skew_s) < 5.0, "lokale Quelle, kein echter Versatz"
    assert (
        metrics.registry.get_sample_value(
            "connector_clock_skew_seconds", {"connector": "throttle-test", "source": "mock"}
        )
        is not None
    )
