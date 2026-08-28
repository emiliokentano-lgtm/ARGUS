"""Fehlerklassifikation, Backoff und Circuit Breaker."""

from __future__ import annotations

import asyncio
import random

import httpx
import pytest

from argus_connector.retry import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    ConnectorError,
    ErrorKind,
    RetryPolicy,
    classify,
    is_retryable,
    retry_async,
)


def _response(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.invalid/x")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError("fehler", request=request, response=response)


class TestClassify:
    @pytest.mark.parametrize(
        ("exc", "expected"),
        [
            (_response(429), ErrorKind.RATE_LIMITED),
            (_response(500), ErrorKind.SERVER_ERROR),
            (_response(503), ErrorKind.SERVER_ERROR),
            (_response(404), ErrorKind.CLIENT_ERROR),
            (_response(401), ErrorKind.CLIENT_ERROR),
            (httpx.ConnectTimeout("zu langsam"), ErrorKind.TIMEOUT),
            (httpx.ReadTimeout("zu langsam"), ErrorKind.TIMEOUT),
            (httpx.ConnectError("Name or service not known"), ErrorKind.DNS),
            (httpx.ConnectError("certificate verify failed"), ErrorKind.TLS),
            (httpx.ConnectError("connection refused"), ErrorKind.CONNECT),
            (ValueError("kein JSON"), ErrorKind.INVALID_PAYLOAD),
            (TimeoutError(), ErrorKind.TIMEOUT),
            (RuntimeError("was auch immer"), ErrorKind.UNKNOWN),
        ],
    )
    def test_classification(self, exc, expected):
        assert classify(exc) is expected

    def test_dns_tls_and_connect_are_distinguished(self):
        """Die Unterscheidung ist im Betrieb der Unterschied zwischen
        'Netz pruefen', 'Zertifikat pruefen' und 'Dienst pruefen'."""
        kinds = {
            classify(httpx.ConnectError("Temporary failure in name resolution")),
            classify(httpx.ConnectError("SSL: CERTIFICATE_VERIFY_FAILED")),
            classify(httpx.ConnectError("Connection refused")),
        }
        assert kinds == {ErrorKind.DNS, ErrorKind.TLS, ErrorKind.CONNECT}

    def test_client_errors_are_not_retried(self):
        assert not is_retryable(_response(404))
        assert not is_retryable(_response(403))

    def test_server_errors_and_throttling_are_retried(self):
        assert is_retryable(_response(500))
        assert is_retryable(_response(429))

    def test_connector_error_carries_its_kind(self):
        exc = ConnectorError("leer", kind=ErrorKind.EMPTY_RESPONSE)
        assert classify(exc) is ErrorKind.EMPTY_RESPONSE
        assert exc.retryable


class TestRetryPolicy:
    def test_delay_grows_exponentially_without_jitter(self):
        policy = RetryPolicy(base_delay_s=1.0, max_delay_s=100.0, jitter=False)
        assert [policy.delay_for(i) for i in range(1, 5)] == [1.0, 2.0, 4.0, 8.0]

    def test_delay_is_capped(self):
        policy = RetryPolicy(base_delay_s=1.0, max_delay_s=5.0, jitter=False)
        assert policy.delay_for(10) == 5.0

    def test_full_jitter_stays_within_the_ceiling(self):
        policy = RetryPolicy(base_delay_s=1.0, max_delay_s=100.0, jitter=True)
        rng = random.Random(42)
        for attempt in range(1, 8):
            ceiling = min(100.0, 1.0 * 2 ** (attempt - 1))
            for _ in range(50):
                assert 0.0 <= policy.delay_for(attempt, rng=rng) <= ceiling

    def test_full_jitter_actually_spreads(self):
        """Voller Jitter verteilt die Wiederkehr - sonst kommen nach einem
        Ausfall alle Konnektoren im selben Moment zurueck."""
        policy = RetryPolicy(base_delay_s=1.0, jitter=True)
        rng = random.Random(7)
        values = [policy.delay_for(5, rng=rng) for _ in range(100)]
        assert len(set(values)) > 90
        assert min(values) < 4.0 < max(values)

    def test_attempt_is_one_based(self):
        with pytest.raises(ValueError):
            RetryPolicy().delay_for(0)


class TestCircuitBreaker:
    def test_opens_after_threshold(self, clock):
        breaker = CircuitBreaker(failure_threshold=3, reset_timeout_s=10, clock=clock)
        for _ in range(2):
            breaker.on_failure()
        assert breaker.state is CircuitState.CLOSED
        breaker.on_failure()
        assert breaker.state is CircuitState.OPEN

    def test_blocks_requests_while_open(self, clock):
        breaker = CircuitBreaker(failure_threshold=1, reset_timeout_s=10, clock=clock)
        breaker.on_failure()
        with pytest.raises(CircuitOpenError) as excinfo:
            breaker.before_request()
        assert excinfo.value.retry_after_s == pytest.approx(10.0)

    def test_half_opens_after_the_timeout(self, clock):
        breaker = CircuitBreaker(failure_threshold=1, reset_timeout_s=10, clock=clock)
        breaker.on_failure()
        clock.advance(11)
        breaker.before_request()
        assert breaker.state is CircuitState.HALF_OPEN

    def test_closes_after_enough_successes(self, clock):
        breaker = CircuitBreaker(
            failure_threshold=1, reset_timeout_s=10, success_threshold=2, clock=clock
        )
        breaker.on_failure()
        clock.advance(11)
        breaker.before_request()
        breaker.on_success()
        assert breaker.state is CircuitState.HALF_OPEN
        breaker.on_success()
        assert breaker.state is CircuitState.CLOSED

    def test_failed_probe_reopens_immediately(self, clock):
        """Ein gescheiterter Testabruf oeffnet sofort wieder - nicht erst nach
        erneutem Erreichen der Schwelle."""
        breaker = CircuitBreaker(failure_threshold=3, reset_timeout_s=10, clock=clock)
        for _ in range(3):
            breaker.on_failure()
        clock.advance(11)
        breaker.before_request()
        breaker.on_failure()
        assert breaker.state is CircuitState.OPEN
        with pytest.raises(CircuitOpenError):
            breaker.before_request()

    def test_success_resets_the_failure_count(self, clock):
        breaker = CircuitBreaker(failure_threshold=3, clock=clock)
        breaker.on_failure()
        breaker.on_failure()
        breaker.on_success()
        breaker.on_failure()
        assert breaker.state is CircuitState.CLOSED


class TestRetryAsync:
    async def test_returns_on_first_success(self):
        calls = 0

        async def op():
            nonlocal calls
            calls += 1
            return "ok"

        assert await retry_async(op, policy=RetryPolicy()) == "ok"
        assert calls == 1

    async def test_retries_transient_errors(self):
        calls = 0

        async def op():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise _response(503)
            return calls

        result = await retry_async(
            op,
            policy=RetryPolicy(max_attempts=5, base_delay_s=0, jitter=False),
            sleep=lambda _: asyncio.sleep(0),
        )
        assert result == 3

    async def test_does_not_retry_permanent_errors(self):
        calls = 0

        async def op():
            nonlocal calls
            calls += 1
            raise _response(404)

        with pytest.raises(httpx.HTTPStatusError):
            await retry_async(op, policy=RetryPolicy(max_attempts=5, base_delay_s=0))
        assert calls == 1, "ein 404 wird beim naechsten Mal auch ein 404 sein"

    async def test_gives_up_after_max_attempts(self):
        calls = 0

        async def op():
            nonlocal calls
            calls += 1
            raise _response(500)

        with pytest.raises(httpx.HTTPStatusError):
            await retry_async(
                op,
                policy=RetryPolicy(max_attempts=3, base_delay_s=0, jitter=False),
                sleep=lambda _: asyncio.sleep(0),
            )
        assert calls == 3

    async def test_retry_after_hint_wins_over_backoff(self):
        delays: list[float] = []

        async def op():
            raise _response(429)

        async def record(seconds: float) -> None:
            delays.append(seconds)

        with pytest.raises(httpx.HTTPStatusError):
            await retry_async(
                op,
                policy=RetryPolicy(max_attempts=2, base_delay_s=0.001, jitter=False),
                sleep=record,
                retry_after_hint=lambda _: 42.0,
            )
        assert delays == [42.0], "die Quelle weiss besser, wann sie wieder kann"

    async def test_client_errors_do_not_trip_the_breaker(self, clock):
        """Ein 404 ist kein Zeichen dafuer, dass die Quelle krank ist."""
        breaker = CircuitBreaker(failure_threshold=2, clock=clock)

        async def op():
            raise _response(404)

        for _ in range(3):
            with pytest.raises(httpx.HTTPStatusError):
                await retry_async(op, policy=RetryPolicy(max_attempts=1), breaker=breaker)
        assert breaker.state is CircuitState.CLOSED

    async def test_server_errors_trip_the_breaker(self, clock):
        breaker = CircuitBreaker(failure_threshold=2, clock=clock)

        async def op():
            raise _response(500)

        for _ in range(2):
            with pytest.raises(httpx.HTTPStatusError):
                await retry_async(
                    op,
                    policy=RetryPolicy(max_attempts=1),
                    breaker=breaker,
                    sleep=lambda _: asyncio.sleep(0),
                )
        assert breaker.state is CircuitState.OPEN

    async def test_cancellation_is_not_swallowed(self):
        async def op():
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await retry_async(op, policy=RetryPolicy(max_attempts=3))

    async def test_error_callback_reports_kind_and_delay(self):
        seen: list[tuple[ErrorKind, int, float]] = []

        async def op():
            raise _response(500)

        with pytest.raises(httpx.HTTPStatusError):
            await retry_async(
                op,
                policy=RetryPolicy(max_attempts=2, base_delay_s=0.001, jitter=False),
                on_error=lambda kind, attempt, delay: seen.append((kind, attempt, delay)),
                sleep=lambda _: asyncio.sleep(0),
            )
        assert [s[0] for s in seen] == [ErrorKind.SERVER_ERROR, ErrorKind.SERVER_ERROR]
        assert [s[1] for s in seen] == [1, 2]
