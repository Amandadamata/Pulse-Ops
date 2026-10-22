"""Transporte protegido: valida e conecta no mesmo IP (T3, T7) e mantém Host/SNI."""

import ipaddress

import httpcore
import pytest

from pulseops.security.transport import (
    GuardedNetworkBackend,
    build_guarded_client,
    validate_destination,
)
from pulseops.security.url_policy import DestinationPolicy, UnsafeDestinationError
from tests.support import FakeResolver

RESPONSE = b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n"


class RecordingStream(httpcore.AsyncNetworkStream):
    def __init__(self) -> None:
        self.written = b""
        self._sent = False

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:  # noqa: ASYNC109
        if self._sent:
            return b""
        self._sent = True
        return RESPONSE

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:  # noqa: ASYNC109
        self.written += buffer

    async def aclose(self) -> None:
        pass


class RecordingBackend(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self.connections: list[tuple[str, int]] = []
        self.stream = RecordingStream()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):  # noqa: ASYNC109
        self.connections.append((host, port))
        return self.stream

    async def sleep(self, seconds: float) -> None:
        pass


def guarded_client(resolver: FakeResolver, inner: RecordingBackend):
    client = build_guarded_client(
        DestinationPolicy(), max_connections=5, user_agent="teste", resolver=resolver
    )
    # Mesmo backend protegido, mas o socket "de verdade" é o de gravação.
    client._transport._pool._network_backend = GuardedNetworkBackend(
        DestinationPolicy(), resolver, inner
    )  # type: ignore[attr-defined]
    return client


async def test_connects_to_validated_ip_and_keeps_host_header() -> None:
    resolver = FakeResolver({"api.example.com": ["93.184.216.34"]})
    inner = RecordingBackend()
    async with guarded_client(resolver, inner) as client:
        response = await client.get("http://api.example.com/health")
    assert response.status_code == 204
    assert inner.connections == [("93.184.216.34", 80)]  # conectou no IP validado
    assert b"Host: api.example.com\r\n" in inner.stream.written  # Host original preservado


async def test_rebinding_is_checked_at_connect_time() -> None:
    """O nome era público no cadastro e passa a apontar para a rede interna."""
    resolver = FakeResolver({"rebind.example.com": ["93.184.216.34"]})
    await validate_destination(DestinationPolicy(), "http://rebind.example.com/", resolver)

    resolver.mapping["rebind.example.com"] = ["127.0.0.1"]
    inner = RecordingBackend()
    async with guarded_client(resolver, inner) as client:
        with pytest.raises(UnsafeDestinationError, match="loopback"):
            await client.get("http://rebind.example.com/")
    assert inner.connections == []  # nenhuma conexão foi aberta


async def test_mixed_public_and_private_answers_are_refused() -> None:
    resolver = FakeResolver({"misto.example.com": ["93.184.216.34", "10.0.0.7"]})
    inner = RecordingBackend()
    async with guarded_client(resolver, inner) as client:
        with pytest.raises(UnsafeDestinationError, match="privado"):
            await client.get("http://misto.example.com/")
    assert inner.connections == []


async def test_name_resolving_to_metadata_is_refused_at_registration() -> None:
    resolver = FakeResolver({"meta.example.com": ["169.254.169.254"]})
    with pytest.raises(UnsafeDestinationError, match="link-local"):
        await validate_destination(DestinationPolicy(), "http://meta.example.com/", resolver)


async def test_unresolvable_name_is_accepted_at_registration() -> None:
    await validate_destination(DestinationPolicy(), "https://fora-do-ar.invalid/", FakeResolver())


async def test_dns_failure_becomes_connect_error() -> None:
    backend = GuardedNetworkBackend(DestinationPolicy(), FakeResolver(), RecordingBackend())
    with pytest.raises(httpcore.ConnectError):
        await backend.connect_tcp("x.invalid", 443)


async def test_clients_ignore_proxy_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """T7: com HTTP(S)_PROXY definido, a conexão continua indo direto ao IP validado."""
    monkeypatch.setenv("HTTP_PROXY", "http://10.9.9.9:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://10.9.9.9:3128")
    resolver = FakeResolver({"api.example.com": ["93.184.216.34"]})
    inner = RecordingBackend()
    async with guarded_client(resolver, inner) as client:
        await client.get("http://api.example.com/")
    assert inner.connections == [("93.184.216.34", 80)]


async def test_redirects_are_not_followed_by_default() -> None:
    client = build_guarded_client(DestinationPolicy(), max_connections=1, user_agent="t")
    assert client.follow_redirects is False
    await client.aclose()


def test_ip_literal_in_policy_check() -> None:
    with pytest.raises(UnsafeDestinationError):
        DestinationPolicy().check_address("x", 80, ipaddress.ip_address("192.168.0.1"))
