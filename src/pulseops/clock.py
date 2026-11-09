"""Replaceable clock: domain code never calls datetime.now() directly."""

import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Current instant in UTC, timezone-aware."""
        ...

    def monotonic(self) -> float:
        """Seconds from a clock that never goes backwards; only for measuring durations."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()
