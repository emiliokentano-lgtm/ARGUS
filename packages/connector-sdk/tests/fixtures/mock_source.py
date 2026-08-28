"""Mock-Quelle fuer die Integrationstests.

Ein kleiner HTTP-Server mit zwei Betriebsarten:

* /records?cursor=N&limit=M  - seitenweise durchnummerierte Datensaetze
* /throttled                 - antwortet die ersten Aufrufe mit HTTP 429

Bewusst kein Framework: ein Thread mit http.server genuegt, laeuft ueberall und
bringt keine weitere Abhaengigkeit mit.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class MockSourceState:
    def __init__(self, total: int = 500, delay_s: float = 0.0) -> None:
        self.total = total
        self.delay_s = delay_s
        self.requests = 0
        self.request_times: list[float] = []
        # Drosselung
        self.throttle_remaining = 0
        self.retry_after: str | None = None
        self.throttle_hits = 0
        self.lock = threading.Lock()


def make_handler(state: MockSourceState):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:
            return

        def _send(self, status: int, payload: dict, extra_headers: dict | None = None) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Date", self.date_time_string())
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)

            with state.lock:
                state.requests += 1
                state.request_times.append(time.monotonic())
                throttling = state.throttle_remaining > 0
                if throttling:
                    state.throttle_remaining -= 1
                    state.throttle_hits += 1
                    retry_after = state.retry_after

            if throttling:
                headers = {"Retry-After": retry_after} if retry_after else {}
                self._send(429, {"error": "zu viele Anfragen"}, headers)
                return

            if state.delay_s:
                time.sleep(state.delay_s)

            cursor = int(params.get("cursor", ["0"])[0])
            limit = int(params.get("limit", ["50"])[0])
            end = min(cursor + limit, state.total)
            records = [
                {"id": i, "value": f"satz-{i}", "ts": 1_700_000_000 + i} for i in range(cursor, end)
            ]
            self._send(
                200,
                {"records": records, "next_cursor": end, "has_more": end < state.total},
            )

    return Handler


class MockSource:
    """Kontextmanager um den Server."""

    def __init__(self, total: int = 500, delay_s: float = 0.0) -> None:
        self.state = MockSourceState(total=total, delay_s=delay_s)
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.state))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def throttle_next(self, count: int, retry_after: str | None = None) -> None:
        with self.state.lock:
            self.state.throttle_remaining = count
            self.state.retry_after = retry_after

    def __enter__(self) -> MockSource:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
