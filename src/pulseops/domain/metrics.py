"""Metric formulas (RF05). The queries live in services/queries.py."""

import math
from collections.abc import Sequence
from datetime import datetime, timedelta


def nearest_rank(values: Sequence[float], percentile: float) -> float | None:
    """Percentile by the nearest-rank method: the value at position ceil(p/100 x n), 1-indexed.

    Returns None when there are no samples, so the interface shows "N/A".
    """
    if not 0 < percentile <= 100:
        raise ValueError("percentile must be in (0, 100]")
    if not values:
        return None
    ordered = sorted(values)
    rank = math.ceil(percentile / 100 * len(ordered))
    return ordered[rank - 1]


def ratio(part: int, total: int) -> float | None:
    """Ratio as a percentage, or None when there is no base (it never invents 0% or 100%)."""
    if total <= 0:
        return None
    return 100.0 * part / total


def clipped_duration(
    window_start: datetime,
    window_end: datetime,
    started_at: datetime,
    ended_at: datetime | None,
    now: datetime,
) -> timedelta:
    """The part of an incident that falls inside the window [start, end).

    An incident that is still open counts until `now` (or the end of the window, if earlier).
    """
    end = min(window_end, ended_at or now)
    start = max(window_start, started_at)
    return max(end - start, timedelta(0))
