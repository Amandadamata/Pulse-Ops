"""Check result categories and what counts as a target failure."""

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
        """Failure of the monitored service (RF03.1). PulseOps internal errors do not count."""
        return self in _FAILURES

    @property
    def is_success(self) -> bool:
        """Answered with an accepted status, fast or slow (RF03.2)."""
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
    Outcome.HEALTHY: "Healthy",
    Outcome.SLOW: "Slow",
    Outcome.UNEXPECTED_STATUS: "Unexpected status",
    Outcome.TIMEOUT: "Timeout",
    Outcome.CONNECTION_ERROR: "Connection/DNS failure",
    Outcome.TLS_ERROR: "TLS failure",
    Outcome.BLOCKED: "Destination blocked",
    Outcome.INTERNAL_ERROR: "PulseOps internal error",
}
