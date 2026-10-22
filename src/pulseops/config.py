"""Configuração lida de variáveis de ambiente com prefixo PULSEOPS_."""

from functools import cached_property
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PULSEOPS_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://pulseops:pulseops@localhost:5432/pulseops"
    log_level: str = "INFO"

    demo_mode: bool = False
    # Pares host:porta separados por vírgula. Só têm efeito com demo_mode ligado.
    demo_allowed_hosts: str = ""
    allowed_ports: str = "80,443,8080,8443"

    cookie_secure: bool = False
    session_ttl_minutes: int = Field(default=480, ge=5, le=7 * 24 * 60)
    display_timezone: str = "America/Sao_Paulo"

    worker_concurrency: int = Field(default=20, ge=1, le=200)
    worker_tick_seconds: float = Field(default=1.0, gt=0, le=10)
    worker_stale_after_seconds: int = Field(default=30, ge=5)
    heartbeat_interval_seconds: float = Field(default=5.0, gt=0)

    webhook_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    webhook_max_attempts: int = Field(default=6, ge=1, le=20)
    webhook_backoff_base_seconds: float = Field(default=5.0, gt=0)
    webhook_backoff_max_seconds: float = Field(default=300.0, gt=0)

    check_retention_days: int = Field(default=30, ge=1)

    @field_validator("display_timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        # ZoneInfoNotFoundError herda de KeyError, que o Pydantic não converte em erro de
        # validação; por isso a conversão explícita para ValueError.
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"fuso horário desconhecido: {value}") from exc
        return value

    @cached_property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.display_timezone)

    @cached_property
    def allowed_port_set(self) -> frozenset[int]:
        return frozenset(int(p) for p in self.allowed_ports.split(",") if p.strip())

    @cached_property
    def demo_allowlist(self) -> frozenset[tuple[str, int]]:
        """Hosts nominais liberados para o laboratório. Vazio fora do modo demo."""
        if not self.demo_mode:
            return frozenset()
        pairs = set()
        for item in self.demo_allowed_hosts.split(","):
            item = item.strip().lower()
            if not item:
                continue
            host, _, port = item.rpartition(":")
            if not host or not port.isdigit():
                raise ValueError(f"PULSEOPS_DEMO_ALLOWED_HOSTS: use host:porta, recebido {item!r}")
            pairs.add((host, int(port)))
        return frozenset(pairs)

    @property
    def min_interval_seconds(self) -> int:
        return 2 if self.demo_mode else 30
