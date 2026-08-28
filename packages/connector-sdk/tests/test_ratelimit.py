"""Token-Bucket und adaptive Drosselung."""

from __future__ import annotations

import pytest

from argus_connector.ratelimit import AdaptiveRateLimiter, TokenBucket, parse_retry_after


class TestTokenBucket:
    async def test_burst_is_available_immediately(self, clock):
        bucket = TokenBucket(rate=1.0, burst=5, clock=clock, sleep=clock.sleep)
        for _ in range(5):
            assert await bucket.acquire() == 0.0
        assert clock.total_slept == 0.0

    async def test_waits_once_the_burst_is_used_up(self, clock):
        bucket = TokenBucket(rate=2.0, burst=2, clock=clock, sleep=clock.sleep)
        await bucket.acquire()
        await bucket.acquire()
        waited = await bucket.acquire()
        assert waited == pytest.approx(0.5, abs=1e-6)

    async def test_tokens_refill_over_time(self, clock):
        bucket = TokenBucket(rate=10.0, burst=1, clock=clock, sleep=clock.sleep)
        await bucket.acquire()
        clock.advance(1.0)
        assert await bucket.acquire() == 0.0

    async def test_refill_is_capped_at_burst(self, clock):
        bucket = TokenBucket(rate=10.0, burst=2, clock=clock, sleep=clock.sleep)
        clock.advance(100.0)  # theoretisch 1000 Tokens
        await bucket.acquire()
        await bucket.acquire()
        assert await bucket.acquire() > 0, "der Eimer darf nicht ueberlaufen"

    async def test_rate_change_takes_effect_immediately(self, clock):
        bucket = TokenBucket(rate=100.0, burst=1, clock=clock, sleep=clock.sleep)
        await bucket.acquire()
        bucket.set_rate(1.0)
        assert await bucket.acquire() == pytest.approx(1.0, abs=1e-6)

    def test_rejects_impossible_configuration(self):
        with pytest.raises(ValueError):
            TokenBucket(rate=0, burst=1)
        with pytest.raises(ValueError):
            TokenBucket(rate=1, burst=0)

    async def test_request_larger_than_bucket_is_an_error(self, clock):
        bucket = TokenBucket(rate=1.0, burst=2, clock=clock, sleep=clock.sleep)
        with pytest.raises(ValueError, match="Eimer"):
            await bucket.acquire(5)


class TestRetryAfter:
    def test_parses_seconds(self):
        assert parse_retry_after("120") == 120.0

    def test_parses_http_date(self):
        """Beide erlaubten Formen kommen in freier Wildbahn vor."""
        import email.utils
        from datetime import UTC, datetime

        target = datetime(2026, 10, 21, 7, 28, 10, tzinfo=UTC)
        header = email.utils.format_datetime(target)
        # Referenzzeit 10 Sekunden davor.
        result = parse_retry_after(header, now=target.timestamp() - 10)
        assert result == pytest.approx(10.0, abs=1.0)

    def test_none_and_garbage(self):
        assert parse_retry_after(None) is None
        assert parse_retry_after("") is None
        assert parse_retry_after("bald") is None

    def test_never_negative(self):
        assert parse_retry_after("-5") == 0.0


class TestAdaptiveRateLimiter:
    def _limiter(self, clock, **kwargs):
        defaults: dict[str, object] = {
            "requests_per_second": 10.0,
            "burst": 10,
            "backoff_factor": 0.5,
            "recovery_step": 0.25,
            "recovery_interval_s": 30.0,
            "min_requests_per_second": 0.5,
        }
        defaults.update(kwargs)
        return AdaptiveRateLimiter(clock=clock, sleep=clock.sleep, **defaults)

    async def test_throttling_halves_the_rate(self, clock):
        limiter = self._limiter(clock)
        assert limiter.current_rate == 10.0
        limiter.on_throttled()
        assert limiter.current_rate == 5.0
        limiter.on_throttled()
        assert limiter.current_rate == 2.5

    async def test_rate_never_falls_below_the_floor(self, clock):
        limiter = self._limiter(clock, min_requests_per_second=1.0)
        for _ in range(20):
            limiter.on_throttled()
        assert limiter.current_rate == 1.0

    async def test_retry_after_pauses_before_the_next_request(self, clock):
        limiter = self._limiter(clock)
        limiter.on_throttled(retry_after_s=30.0)
        waited = await limiter.acquire()
        assert waited >= 30.0, "die Pause der Quelle muss eingehalten werden"

    async def test_recovery_is_gradual(self, clock):
        limiter = self._limiter(clock)
        limiter.on_throttled()
        assert limiter.current_rate == 5.0
        # Zu frueh: nichts passiert.
        clock.advance(10.0)
        await limiter.acquire()
        assert limiter.current_rate == 5.0
        # Nach dem Intervall: ein Schritt.
        clock.advance(25.0)
        await limiter.acquire()
        assert limiter.current_rate == pytest.approx(7.5)

    async def test_recovery_stops_at_the_configured_rate(self, clock):
        limiter = self._limiter(clock)
        limiter.on_throttled()
        for _ in range(20):
            clock.advance(31.0)
            await limiter.acquire()
        assert limiter.current_rate == 10.0

    async def test_politeness_delay_is_respected(self, clock):
        limiter = self._limiter(clock, politeness_delay_s=2.0)
        await limiter.acquire()
        waited = await limiter.acquire()
        assert waited >= 2.0

    async def test_delay_callback_reports_waiting_time(self, clock):
        seen: list[float] = []
        limiter = self._limiter(clock, requests_per_second=1.0, burst=1)
        limiter._on_delay = seen.append
        await limiter.acquire()
        await limiter.acquire()
        assert seen and seen[0] > 0

    async def test_rate_change_callback_fires(self, clock):
        rates: list[float] = []
        limiter = self._limiter(clock)
        limiter._on_rate_change = rates.append
        limiter.on_throttled()
        assert rates == [5.0]

    async def test_throttle_events_are_counted(self, clock):
        limiter = self._limiter(clock)
        limiter.on_throttled()
        limiter.on_throttled()
        assert limiter.throttle_events == 2
