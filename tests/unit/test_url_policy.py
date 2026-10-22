"""Cenário 22: bloqueios SSRF na validação da URL e dos endereços (T1, T2, T5, T6, T9)."""

import ipaddress

import pytest

from pulseops.config import Settings
from pulseops.security.url_policy import DestinationPolicy, UnsafeDestinationError, blocked_reason

policy = DestinationPolicy()


@pytest.mark.parametrize(
    "url",
    [
        "https://api.example.com/health",
        "http://api.example.com:8080/x?y=1",
        "https://93.184.216.34/",
        "https://[2606:4700:4700::1111]/",
    ],
)
def test_allowed_urls(url: str) -> None:
    policy.validate_url(url)


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("ftp://example.com/", "http"),
        ("file:///etc/passwd", "http"),
        ("gopher://example.com/", "http"),
        ("https://user:pass@example.com/", "credenciais"),
        ("https://user@example.com/", "credenciais"),
        ("https://example.com:22/", "porta 22"),
        ("https://example.com:5432/", "porta 5432"),
        ("https://example.com:99999/", "URL inválida"),
        ("https:///sem-host", "sem host"),
        ("http://127.0.0.1/", "loopback"),
        ("http://localhost.:80/", None),  # nome: só é barrado na resolução (ver test_transport)
        ("http://10.0.0.1/", "privado"),
        ("http://172.16.5.4/", "privado"),
        ("http://192.168.1.1/", "privado"),
        ("http://169.254.169.254/latest/meta-data/", "link-local"),
        ("http://100.64.0.1/", "reservado"),
        ("http://0.0.0.0/", "não especificado"),
        ("http://224.0.0.1/", "multicast"),
        ("http://[::1]/", "loopback"),
        ("http://[fe80::1]/", "link-local"),
        ("http://[fd00:ec2::254]/", "privado"),
        ("http://[::ffff:127.0.0.1]/", "loopback"),
        ("http://[::ffff:10.0.0.1]/", "privado"),
        ("http://[64:ff9b::a00:1]/", "privado"),  # NAT64 de 10.0.0.1
        ("http://[2002:7f00:1::]/", "loopback"),  # 6to4 de 127.0.0.1
        ("http://2130706433/", "não canônica"),  # 127.0.0.1 em decimal
        ("http://0x7f000001/", "não canônica"),
        ("http://0177.0.0.1/", "não canônica"),
        ("http://0x7f.1/", "não canônica"),
        ("http://127.1/", "não canônica"),
    ],
)
def test_blocked_urls(url: str, message: str | None) -> None:
    if message is None:
        policy.validate_url(url)
        return
    with pytest.raises(UnsafeDestinationError, match=message):
        policy.validate_url(url)


def test_public_addresses_have_no_block_reason() -> None:
    assert blocked_reason(ipaddress.ip_address("8.8.8.8")) is None
    assert blocked_reason(ipaddress.ip_address("2001:4860:4860::8888")) is None


def test_demo_allowlist_is_nominal_and_port_specific() -> None:
    demo = DestinationPolicy(demo_allowlist=frozenset({("lab-target", 8081)}))
    demo.validate_url("http://lab-target:8081/service")
    demo.check_address("lab-target", 8081, ipaddress.ip_address("172.18.0.5"))
    with pytest.raises(UnsafeDestinationError):
        demo.validate_url("http://lab-target:9999/")  # outra porta não está liberada
    with pytest.raises(UnsafeDestinationError):
        demo.check_address("outro-host", 8081, ipaddress.ip_address("172.18.0.5"))
    with pytest.raises(UnsafeDestinationError):
        demo.validate_url("http://172.18.0.5:8081/")  # liberar o nome não libera o IP


def test_demo_allowlist_is_ignored_outside_demo_mode() -> None:
    off = Settings(demo_mode=False, demo_allowed_hosts="lab-target:8081")
    on = Settings(demo_mode=True, demo_allowed_hosts="lab-target:8081, Lab-Receiver:8082")
    assert off.demo_allowlist == frozenset()
    assert on.demo_allowlist == {("lab-target", 8081), ("lab-receiver", 8082)}


def test_demo_allowlist_requires_host_and_port() -> None:
    with pytest.raises(ValueError):
        _ = Settings(demo_mode=True, demo_allowed_hosts="10.0.0.0/8").demo_allowlist
