"""Logs em JSON com contexto (monitor, execução, incidente) e mascaramento de segredos."""

import json
import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

_context: ContextVar[dict[str, Any] | None] = ContextVar("log_context", default=None)

_SENSITIVE_KEYS = ("password", "senha", "token", "secret", "authorization", "cookie", "csrf")
_URL_QUERY = re.compile(r"(https?://[^\s?#\"']+)\?[^\s\"'#]*")
_URL_USERINFO = re.compile(r"(https?://)[^/\s@\"']+@")

# Atributos que todo LogRecord tem; o resto veio de `extra=` e vai para o JSON.
_RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime"}


def redact_text(text: str) -> str:
    text = _URL_USERINFO.sub(r"\1[redacted]@", text)
    return _URL_QUERY.sub(r"\1?[redacted]", text)


def redact_value(key: str, value: Any) -> Any:
    if any(word in key.lower() for word in _SENSITIVE_KEYS):
        return "[redacted]"
    if isinstance(value, str):
        return redact_text(value)
    return value


@contextmanager
def log_context(**fields: Any) -> Iterator[None]:
    """Acrescenta campos a todos os logs emitidos dentro do bloco (inclusive em corrotinas)."""
    current = _context.get() or {}
    token = _context.set({**current, **fields})
    try:
        yield
    finally:
        _context.reset(token)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact_text(record.getMessage()),
        }
        for key, value in (_context.get() or {}).items():
            payload[key] = redact_value(key, value)
        for key, value in vars(record).items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = redact_value(key, value)
        if record.exc_info:
            payload["error"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # O log de acesso do uvicorn imprime a URL inteira; o nosso formatador mascara a query.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).handlers[:] = []
        logging.getLogger(name).propagate = True
    logging.getLogger("httpx").setLevel(logging.WARNING)
