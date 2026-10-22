"""Política de destino contra SSRF (ver docs/modelo-de-ameacas.md e ADR 0005).

Duas camadas:
1. `validate_url` olha só o texto da URL (cadastro de monitor e de webhook).
2. `check_address` decide se um IP já resolvido pode ser usado. É chamada pelo
   transporte no momento da conexão, então vale também contra DNS rebinding.
"""

import ipaddress
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

# Hosts formados só por números/hex com pontos: "2130706433", "0x7f.1", "0177.0.0.1".
# O resolvedor do sistema aceita essas formas; aqui só a forma canônica passa.
_NUMERIC_HOST = re.compile(r"^(0x[0-9a-f]*|[0-9]+)(\.(0x[0-9a-f]*|[0-9]+))*\.?$")
_NAT64_PREFIX = ipaddress.IPv6Network("64:ff9b::/96")


class UnsafeDestinationError(ValueError):
    """Destino recusado pela política. A mensagem é segura para mostrar ao operador."""


@dataclass(frozen=True)
class Destination:
    scheme: str
    host: str
    port: int


@dataclass(frozen=True)
class DestinationPolicy:
    allowed_ports: frozenset[int] = frozenset({80, 443, 8080, 8443})
    # Pares (host, porta) do laboratório. Só é preenchido em modo demonstração.
    demo_allowlist: frozenset[tuple[str, int]] = field(default_factory=frozenset)

    def validate_url(self, url: str) -> Destination:
        try:
            parts = urlsplit(url.strip())
            port = parts.port
        except ValueError as exc:
            raise UnsafeDestinationError("URL inválida") from exc

        scheme = parts.scheme.lower()
        if scheme not in ("http", "https"):
            raise UnsafeDestinationError("use http:// ou https://")
        if parts.username is not None or parts.password is not None:
            raise UnsafeDestinationError("credenciais na URL não são permitidas")
        host = (parts.hostname or "").lower()
        if not host:
            raise UnsafeDestinationError("URL sem host")
        port = port or (443 if scheme == "https" else 80)

        if self.is_demo_host(host, port):
            return Destination(scheme, host, port)

        if port not in self.allowed_ports:
            allowed = ", ".join(str(p) for p in sorted(self.allowed_ports))
            raise UnsafeDestinationError(f"porta {port} não permitida (permitidas: {allowed})")

        literal = _parse_ip(host)
        if literal is None and _NUMERIC_HOST.match(host):
            raise UnsafeDestinationError("endereço IP em forma não canônica")
        if literal is not None:
            self.check_address(host, port, literal)
        return Destination(scheme, host, port)

    def is_demo_host(self, host: str, port: int) -> bool:
        return (host.lower().rstrip("."), port) in self.demo_allowlist

    def check_address(self, host: str, port: int, address: IPAddress) -> None:
        """Levanta UnsafeDestinationError se o IP não puder ser usado para este host."""
        if self.is_demo_host(host, port):
            return
        reason = blocked_reason(address)
        if reason:
            raise UnsafeDestinationError(f"{host} aponta para {reason} ({address})")


def blocked_reason(address: IPAddress) -> str | None:
    """Motivo do bloqueio, ou None se o endereço for público e unicast."""
    if isinstance(address, ipaddress.IPv6Address):
        embedded = address.ipv4_mapped or address.sixtofour
        if embedded is None and address in _NAT64_PREFIX:
            embedded = ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
        if embedded is not None:
            return blocked_reason(embedded)
        if address.teredo:
            return "endereço Teredo"
    if address.is_loopback:
        return "endereço de loopback"
    if address.is_link_local:
        return "endereço link-local (inclui metadados de nuvem)"
    if address.is_multicast:
        return "endereço multicast"
    if address.is_unspecified:
        return "endereço não especificado"
    if address.is_private:
        return "endereço privado"
    if not address.is_global:
        return "endereço reservado ou não roteável"
    return None


def _parse_ip(host: str) -> IPAddress | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None
