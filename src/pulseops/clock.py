"""Relógio substituível: o código de domínio nunca chama datetime.now() direto."""

import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Instante atual em UTC, com fuso (timezone-aware)."""
        ...

    def monotonic(self) -> float:
        """Segundos de um relógio que nunca volta para trás; só serve para medir durações."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()
