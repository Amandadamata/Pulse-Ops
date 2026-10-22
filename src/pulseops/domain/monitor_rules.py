"""Limites e validações combinadas da configuração de um monitor (RF01)."""

from dataclasses import dataclass

from pulseops.domain.status_codes import parse_status_codes

MAX_INTERVAL_SECONDS = 86_400
MIN_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS = 1, 30
MIN_LATENCY_MS = 50
MIN_THRESHOLD, MAX_THRESHOLD = 1, 10
MAX_NAME, MAX_DESCRIPTION, MAX_URL = 100, 500, 2048
METHODS = ("GET", "HEAD")

# Campos cuja mudança altera o significado dos contadores (RF03.5).
CHECK_FIELDS = (
    "url",
    "method",
    "accepted_status_codes",
    "timeout_seconds",
    "latency_threshold_ms",
    "failure_threshold",
    "recovery_threshold",
)


@dataclass(frozen=True)
class MonitorConfig:
    name: str
    url: str
    method: str = "GET"
    interval_seconds: int = 60
    timeout_seconds: int = 5
    accepted_status_codes: str = "200-299"
    latency_threshold_ms: int = 1000
    failure_threshold: int = 3
    recovery_threshold: int = 2
    description: str = ""


@dataclass(frozen=True)
class FieldError:
    field: str
    message: str


def validate_config(config: MonitorConfig, *, min_interval_seconds: int) -> list[FieldError]:
    """Devolve todos os erros de uma vez, para o formulário mostrar tudo junto."""
    errors: list[FieldError] = []

    def check_range(field: str, value: int, low: int, high: int) -> None:
        if not low <= value <= high:
            errors.append(FieldError(field, f"deve estar entre {low} e {high}"))

    name = config.name.strip()
    if not name or len(name) > MAX_NAME:
        errors.append(FieldError("name", f"obrigatório, até {MAX_NAME} caracteres"))
    if len(config.description) > MAX_DESCRIPTION:
        errors.append(FieldError("description", f"até {MAX_DESCRIPTION} caracteres"))
    if len(config.url) > MAX_URL:
        errors.append(FieldError("url", f"até {MAX_URL} caracteres"))
    if config.method not in METHODS:
        errors.append(FieldError("method", "use GET ou HEAD"))

    check_range(
        "interval_seconds", config.interval_seconds, min_interval_seconds, MAX_INTERVAL_SECONDS
    )
    check_range("timeout_seconds", config.timeout_seconds, MIN_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS)
    check_range("failure_threshold", config.failure_threshold, MIN_THRESHOLD, MAX_THRESHOLD)
    check_range("recovery_threshold", config.recovery_threshold, MIN_THRESHOLD, MAX_THRESHOLD)

    if config.timeout_seconds >= config.interval_seconds:
        errors.append(FieldError("timeout_seconds", "deve ser menor que o intervalo"))

    max_latency = config.timeout_seconds * 1000
    if not MIN_LATENCY_MS <= config.latency_threshold_ms <= max_latency:
        errors.append(
            FieldError(
                "latency_threshold_ms",
                f"deve estar entre {MIN_LATENCY_MS} e {max_latency} (timeout em ms)",
            )
        )

    try:
        parse_status_codes(config.accepted_status_codes)
    except ValueError as exc:
        errors.append(FieldError("accepted_status_codes", str(exc)))

    return errors
