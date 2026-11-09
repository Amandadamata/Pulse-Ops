"""HTTPX transport that only connects to IPs approved by the policy (ADR 0005).

`httpcore` calls the *network backend*'s `connect_tcp(host, port)` to open each
connection. This backend resolves the name, validates every IP and connects to the
validated IP. `httpcore` keeps using the original name in the Host header, in SNI and
in certificate verification, because those values come from the URL, not the socket.
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
        # The loop's getaddrinfo runs in a separate thread: it does not block the event loop.
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
            raise httpcore.ConnectError(f"could not resolve the name: {exc}") from exc
        if not addresses:
            raise httpcore.ConnectError("the name has no addresses")
        # If any address is forbidden, refuse: this avoids picking "the good IP" from an
        # answer that mixes a public IP with an internal one.
        for address in addresses:
            self._policy.check_address(host, port, address)
        return addresses[0]

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore signature
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
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore signature
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise UnsafeDestinationError("Unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def build_guarded_client(
    policy: DestinationPolicy,
    *,
    max_connections: int,
    user_agent: str,
    resolver: Resolver | None = None,
) -> httpx.AsyncClient:
    """HTTPX client with the protected backend, no proxy from the environment and no redirects."""
    transport = httpx.AsyncHTTPTransport(trust_env=False, retries=0)
    # HTTPX 0.28 internal detail: the transport delegates to the pool in `_pool`. We swap the
    # pool for one with our backend. tests/unit/test_transport.py breaks if this changes.
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
    """Validation when registering: the URL text and, if the name resolves, the current IPs.

    A name that does not resolve right now is accepted (the service may be down); the
    real protection happens again on every connection.
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
