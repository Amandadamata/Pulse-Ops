"""Pieces reused by the tests: a controllable clock, a simulated resolver and HTTP target."""

import ipaddress
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx

from pulseops.checks.checker import HttpChecker
from pulseops.security.url_policy import IPAddress

START = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


class FakeClock:
    """Stopped clock that only moves when the test says so. No sleep in the tests."""

    def __init__(self, start: datetime = START) -> None:
        self._now = start
        self._mono = 1000.0

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._mono

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)
        self._mono += seconds


class FakeResolver:
    """Resolves known names to fixed IPs; everything else goes to a fictional public IP."""

    def __init__(self, mapping: dict[str, list[str]] | None = None) -> None:
        self.mapping = mapping or {}
        self.calls: list[str] = []

    async def resolve(self, host: str, port: int) -> list[IPAddress]:
        self.calls.append(host)
        if host in self.mapping:
            return [ipaddress.ip_address(a) for a in self.mapping[host]]
        if host.endswith(".invalid"):
            raise OSError("name not resolved")
        return [ipaddress.ip_address("93.184.216.34")]


class ScriptedTarget:
    """Simulated HTTP target with httpx.MockTransport.

    `mode` picks the answer: "ok", "slow", "error", "timeout", "refused", "tls".
    Slowness is simulated by moving the FakeClock forward, not by sleeping.
    """

    def __init__(self, clock: FakeClock, slow_ms: int = 1500) -> None:
        self.clock = clock
        self.mode = "ok"
        self.slow_ms = slow_ms
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.clock.advance(0.02)
        if self.mode == "slow":
            self.clock.advance(self.slow_ms / 1000)
            return httpx.Response(200, text="ok")
        if self.mode == "error":
            return httpx.Response(500, text="error")
        if self.mode == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if self.mode == "refused":
            raise httpx.ConnectError("[Errno 111] Connection refused", request=request)
        if self.mode == "tls":
            import ssl

            try:
                raise ssl.SSLCertVerificationError(1, "certificate verify failed")
            except ssl.SSLCertVerificationError as exc:
                raise httpx.ConnectError("SSL: CERTIFICATE_VERIFY_FAILED", request=request) from exc
        return httpx.Response(200, text="ok")

    def checker(self) -> HttpChecker:
        client = httpx.AsyncClient(transport=httpx.MockTransport(self.handler))
        return HttpChecker(client, self.clock)


def handler_from(fn: Callable[[httpx.Request], httpx.Response]) -> httpx.MockTransport:
    return httpx.MockTransport(fn)
