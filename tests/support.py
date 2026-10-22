"""Peças reutilizadas pelos testes: relógio controlável, resolvedor e alvo HTTP simulados."""

import ipaddress
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx

from pulseops.checks.checker import HttpChecker
from pulseops.security.url_policy import IPAddress

START = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


class FakeClock:
    """Relógio parado que só anda quando o teste manda. Sem sleep nos testes."""

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
    """Resolve nomes conhecidos para IPs fixos; o resto vai para um IP público fictício."""

    def __init__(self, mapping: dict[str, list[str]] | None = None) -> None:
        self.mapping = mapping or {}
        self.calls: list[str] = []

    async def resolve(self, host: str, port: int) -> list[IPAddress]:
        self.calls.append(host)
        if host in self.mapping:
            return [ipaddress.ip_address(a) for a in self.mapping[host]]
        if host.endswith(".invalid"):
            raise OSError("nome não resolvido")
        return [ipaddress.ip_address("93.184.216.34")]


class ScriptedTarget:
    """Alvo HTTP simulado com httpx.MockTransport.

    `mode` escolhe a resposta: "ok", "slow", "error", "timeout", "refused", "tls".
    A lentidão é simulada avançando o FakeClock, não dormindo.
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
            return httpx.Response(500, text="erro")
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
