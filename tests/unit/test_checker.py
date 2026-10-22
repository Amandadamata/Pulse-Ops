"""Classificação dos checks (RF02): cenários 2, 3 e 4."""

import asyncio
import ssl

import httpx
import pytest

from pulseops.checks.checker import CheckTarget, HttpChecker
from pulseops.domain.outcomes import Outcome
from pulseops.domain.status_codes import parse_status_codes
from pulseops.security.url_policy import UnsafeDestinationError
from tests.support import FakeClock, ScriptedTarget

TARGET = CheckTarget(
    url="https://api.example.com/health?token=segredo",
    method="GET",
    timeout_seconds=5,
    latency_threshold_ms=1000,
    accepted=parse_status_codes("200-299"),
)


async def check_with(mode: str) -> tuple[Outcome, str, int | None]:
    clock = FakeClock()
    target = ScriptedTarget(clock)
    target.mode = mode
    obs = await target.checker().check(TARGET)
    return obs.outcome, obs.explanation, obs.status_code


async def test_healthy() -> None:
    assert await check_with("ok") == (Outcome.HEALTHY, "HTTP 200 em 20 ms", 200)


async def test_slow_200_is_slow_not_failure() -> None:
    """Cenário 2."""
    outcome, explanation, status = await check_with("slow")
    assert (outcome, status) == (Outcome.SLOW, 200)
    assert explanation == "HTTP 200 em 1520 ms (limite 1000 ms)"
    assert not outcome.is_failure


async def test_unexpected_status() -> None:
    """Cenário 3."""
    assert await check_with("error") == (
        Outcome.UNEXPECTED_STATUS,
        "HTTP 500 fora dos status aceitos (200-299)",
        500,
    )


@pytest.mark.parametrize(
    ("mode", "outcome", "text"),
    [
        ("timeout", Outcome.TIMEOUT, "sem resposta em 5 s"),
        ("refused", Outcome.CONNECTION_ERROR, "conexão recusada"),
        ("tls", Outcome.TLS_ERROR, "certificado"),
    ],
)
async def test_network_and_tls_failures(mode: str, outcome: Outcome, text: str) -> None:
    """Cenário 4."""
    got, explanation, status = await check_with(mode)
    assert got is outcome and text in explanation and status is None


async def test_dns_failure_is_connection_error() -> None:
    import socket

    def handler(request: httpx.Request) -> httpx.Response:
        try:
            raise socket.gaierror(-2, "Name or service not known")
        except socket.gaierror as exc:
            raise httpx.ConnectError("falha", request=request) from exc

    checker = HttpChecker(httpx.AsyncClient(transport=httpx.MockTransport(handler)), FakeClock())
    obs = await checker.check(TARGET)
    assert (obs.outcome, obs.explanation) == (
        Outcome.CONNECTION_ERROR,
        "falha de DNS: nome não resolvido",
    )


async def test_tls_handshake_error_without_cert_verification() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        try:
            raise ssl.SSLError("wrong version number")
        except ssl.SSLError as exc:
            raise httpx.ConnectError("handshake", request=request) from exc

    checker = HttpChecker(httpx.AsyncClient(transport=httpx.MockTransport(handler)), FakeClock())
    assert (await checker.check(TARGET)).outcome is Outcome.TLS_ERROR


async def test_total_deadline_is_enforced() -> None:
    async def hang(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)
        return httpx.Response(200)

    checker = HttpChecker(httpx.AsyncClient(transport=httpx.MockTransport(hang)), FakeClock())
    obs = await checker.check(CheckTarget(**{**TARGET.__dict__, "timeout_seconds": 0.05}))
    assert obs.outcome is Outcome.TIMEOUT


async def test_redirect_is_not_followed() -> None:
    """T4: 302 para a rede interna é só um status, não é seguido."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data"})

    checker = HttpChecker(httpx.AsyncClient(transport=httpx.MockTransport(handler)), FakeClock())
    obs = await checker.check(TARGET)
    assert (obs.outcome, obs.status_code) == (Outcome.UNEXPECTED_STATUS, 302)
    assert len(requests) == 1


async def test_blocked_destination_at_connect_time() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise UnsafeDestinationError("api.example.com aponta para endereço privado (10.0.0.1)")

    checker = HttpChecker(httpx.AsyncClient(transport=httpx.MockTransport(handler)), FakeClock())
    obs = await checker.check(TARGET)
    assert obs.outcome is Outcome.BLOCKED and "política de rede" in obs.explanation


async def test_unexpected_exception_is_internal_error_not_target_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise KeyError("bug do PulseOps")

    checker = HttpChecker(httpx.AsyncClient(transport=httpx.MockTransport(handler)), FakeClock())
    obs = await checker.check(TARGET)
    assert obs.outcome is Outcome.INTERNAL_ERROR and not obs.outcome.is_failure


async def test_explanation_never_contains_url_or_query() -> None:
    for mode in ("ok", "slow", "error", "timeout", "refused", "tls"):
        _, explanation, _ = await check_with(mode)
        assert "segredo" not in explanation and "api.example.com" not in explanation


async def test_body_is_not_read() -> None:
    """RF02.4: um corpo enorme não é baixado."""
    produced = 0

    async def huge_body():
        nonlocal produced
        for _ in range(1000):
            produced += 1
            yield b"x" * 65536

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=huge_body())

    checker = HttpChecker(httpx.AsyncClient(transport=httpx.MockTransport(handler)), FakeClock())
    assert (await checker.check(TARGET)).outcome is Outcome.HEALTHY
    assert produced <= 1


async def test_head_method_is_used() -> None:
    clock = FakeClock()
    target = ScriptedTarget(clock)
    await target.checker().check(CheckTarget(**{**TARGET.__dict__, "method": "HEAD"}))
    assert target.requests[0].method == "HEAD"
