"""Categorias de resultado de uma verificação e o que conta como falha do alvo."""

from enum import StrEnum


class Outcome(StrEnum):
    HEALTHY = "healthy"
    SLOW = "slow"
    UNEXPECTED_STATUS = "unexpected_status"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    TLS_ERROR = "tls_error"
    BLOCKED = "blocked"
    INTERNAL_ERROR = "internal_error"

    @property
    def is_failure(self) -> bool:
        """Falha do serviço monitorado (RF03.1). Erro interno do PulseOps não é falha do alvo."""
        return self in _FAILURES

    @property
    def is_success(self) -> bool:
        """Respondeu com status aceito, rápido ou lento (RF03.2)."""
        return self in (Outcome.HEALTHY, Outcome.SLOW)

    @property
    def label(self) -> str:
        return _LABELS[self]


_FAILURES = frozenset(
    {
        Outcome.UNEXPECTED_STATUS,
        Outcome.TIMEOUT,
        Outcome.CONNECTION_ERROR,
        Outcome.TLS_ERROR,
        Outcome.BLOCKED,
    }
)

_LABELS = {
    Outcome.HEALTHY: "Saudável",
    Outcome.SLOW: "Lento",
    Outcome.UNEXPECTED_STATUS: "Status inesperado",
    Outcome.TIMEOUT: "Timeout",
    Outcome.CONNECTION_ERROR: "Falha de conexão/DNS",
    Outcome.TLS_ERROR: "Falha TLS",
    Outcome.BLOCKED: "Destino bloqueado",
    Outcome.INTERNAL_ERROR: "Erro interno do PulseOps",
}
