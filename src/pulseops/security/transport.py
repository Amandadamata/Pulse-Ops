"""Transporte HTTPX que só conecta em IPs aprovados pela política (ADR 0005).

O `httpcore` chama `connect_tcp(host, porta)` do *network backend* para abrir cada
conexão. Este backend resolve o nome, valida todos os IPs e conecta no IP
validado. O `httpcore` continua usando o nome original no header Host, no SNI e
na verificação do certificado, porque esses valores vêm da URL e não do socket.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Iterable
from typing import Any, Protocol

import httpcore
import httpx

from pulseops.security.url_policy import DestinationPolicy, IPAddress, UnsafeDestinationError


class Resolver(Protocol):
    async def resolve(self, host: str, port: int) -> list[IPAddress]: ...


class SystemResolver:
    async def resolve(self, host: str, port: int) -> list[IPAddress]:
        loop = asyncio.get_running_loop()
        # getaddrinfo do loop roda em thread separada: não bloqueia o event loop.
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        return [ipaddress.ip_address(info[4][0]) for info in infos]


class GuardedNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(
        self,
        policy: DestinationPolicy,
        resolver: Resolver | None = None,
        inner: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self._policy = policy
        self._resolver = resolver or SystemResolver()
        self._inner = inner or httpcore.AnyIOBackend()

    async def resolve_allowed(self, host: str, port: int) -> IPAddress:
        try:
            addresses = await self._resolver.resolve(host, port)
        except OSError as exc:
            raise httpcore.ConnectError(f"não foi possível resolver o nome: {exc}") from exc
        if not addresses:
            raise httpcore.ConnectError("o nome não tem endereços")
        # Se qualquer endereço for proibido, recusa: evita escolher "o IP bom" de uma
        # resposta que mistura um IP público com um interno.
        for address in addresses:
            self._policy.check_address(host, port, address)
        return addresses[0]

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - assinatura do httpcore
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        address = await self.resolve_allowed(host, port)
        return await self._inner.connect_tcp(
            str(address), port, timeout, local_address, socket_options
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 - assinatura do httpcore
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise UnsafeDestinationError("sockets Unix não são permitidos")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def build_guarded_client(
    policy: DestinationPolicy,
    *,
    max_connections: int,
    user_agent: str,
    resolver: Resolver | None = None,
) -> httpx.AsyncClient:
    """Cliente HTTPX com o backend protegido, sem proxy do ambiente e sem redirecionamentos."""
    transport = httpx.AsyncHTTPTransport(trust_env=False, retries=0)
    # Detalhe interno do HTTPX 0.28: o transporte delega ao pool em `_pool`. Trocamos o
    # pool por um com o nosso backend. tests/unit/test_transport.py quebra se isso mudar.
    transport._pool = httpcore.AsyncConnectionPool(
        ssl_context=httpx.create_ssl_context(trust_env=False),
        max_connections=max_connections,
        max_keepalive_connections=0,
        network_backend=GuardedNetworkBackend(policy, resolver),
    )
    return httpx.AsyncClient(
        transport=transport,
        trust_env=False,
        follow_redirects=False,
        headers={"User-Agent": user_agent},
    )


async def validate_destination(
    policy: DestinationPolicy, url: str, resolver: Resolver | None = None
) -> None:
    """Validação de cadastro: texto da URL e, se o nome resolver, os IPs atuais.

    Um nome que não resolve agora é aceito (o serviço pode estar fora do ar); a
    proteção definitiva acontece de novo em cada conexão.
    """
    destination = policy.validate_url(url)
    if policy.is_demo_host(destination.host, destination.port):
        return
    try:
        addresses = await (resolver or SystemResolver()).resolve(destination.host, destination.port)
    except OSError:
        return
    for address in addresses:
        policy.check_address(destination.host, destination.port, address)
