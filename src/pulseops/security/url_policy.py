"""Destination policy against SSRF (see docs/modelo-de-ameacas.md and ADR 0005).

Two layers:
1. `validate_url` only looks at the URL text (when registering a monitor or webhook).
2. `check_address` decides whether an already resolved IP can be used. The transport
   calls it at connection time, so it also holds against DNS rebinding.
"""

import ipaddress
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

# Hosts made only of numbers/hex with dots: "2130706433", "0x7f.1", "0177.0.0.1".
# The system resolver accepts these forms; here only the canonical form passes.
_NUMERIC_HOST = re.compile(r"^(0x[0-9a-f]*|[0-9]+)(\.(0x[0-9a-f]*|[0-9]+))*\.?$")
_NAT64_PREFIX = ipaddress.IPv6Network("64:ff9b::/96")


class UnsafeDestinationError(ValueError):
    """Destination refused by the policy. The message is safe to show to the operator."""


@dataclass(frozen=True)
class Destination:
    scheme: str
    host: str
    port: int


@dataclass(frozen=True)
class DestinationPolicy:
    allowed_ports: frozenset[int] = frozenset({80, 443, 8080, 8443})
    # Lab (host, port) pairs. Only filled in demo mode.
    demo_allowlist: frozenset[tuple[str, int]] = field(default_factory=frozenset)

    def validate_url(self, url: str) -> Destination:
        try:
            parts = urlsplit(url.strip())
            port = parts.port
        except ValueError as exc:
            raise UnsafeDestinationError("invalid URL") from exc

        scheme = parts.scheme.lower()
        if scheme not in ("http", "https"):
            raise UnsafeDestinationError("use http:// or https://")
        if parts.username is not None or parts.password is not None:
            raise UnsafeDestinationError("credentials in the URL are not allowed")
        host = (parts.hostname or "").lower()
        if not host:
            raise UnsafeDestinationError("URL without a host")
        port = port or (443 if scheme == "https" else 80)

        if self.is_demo_host(host, port):
            return Destination(scheme, host, port)

        if port not in self.allowed_ports:
            allowed = ", ".join(str(p) for p in sorted(self.allowed_ports))
            raise UnsafeDestinationError(f"port {port} not allowed (allowed: {allowed})")

        literal = _parse_ip(host)
        if literal is None and _NUMERIC_HOST.match(host):
            raise UnsafeDestinationError("IP address in non-canonical form")
        if literal is not None:
            self.check_address(host, port, literal)
        return Destination(scheme, host, port)

    def is_demo_host(self, host: str, port: int) -> bool:
        return (host.lower().rstrip("."), port) in self.demo_allowlist

    def check_address(self, host: str, port: int, address: IPAddress) -> None:
        """Raises UnsafeDestinationError if the IP cannot be used for this host."""
        if self.is_demo_host(host, port):
            return
        reason = blocked_reason(address)
        if reason:
            raise UnsafeDestinationError(f"{host} points to {reason} ({address})")


def blocked_reason(address: IPAddress) -> str | None:
    """Reason for blocking, or None if the address is public and unicast."""
    if isinstance(address, ipaddress.IPv6Address):
        embedded = address.ipv4_mapped or address.sixtofour
        if embedded is None and address in _NAT64_PREFIX:
            embedded = ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
        if embedded is not None:
            return blocked_reason(embedded)
        if address.teredo:
            return "Teredo address"
    if address.is_loopback:
        return "loopback address"
    if address.is_link_local:
        return "link-local address (includes cloud metadata)"
    if address.is_multicast:
        return "multicast address"
    if address.is_unspecified:
        return "unspecified address"
    if address.is_private:
        return "private address"
    if not address.is_global:
        return "reserved or non-routable address"
    return None


def _parse_ip(host: str) -> IPAddress | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None
