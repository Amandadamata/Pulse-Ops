"""Fórmulas de métricas (RF05) — cenário 19 na parte sem banco."""

from datetime import timedelta

import pytest

from pulseops.domain.metrics import clipped_duration, nearest_rank, ratio
from tests.support import START


def test_nearest_rank_without_samples_is_none() -> None:
    assert nearest_rank([], 95) is None


def test_nearest_rank_small_sample_returns_maximum() -> None:
    # ceil(0,95 × 5) = 5 → quinto valor ordenado, que é o máximo.
    assert nearest_rank([30, 10, 50, 20, 40], 95) == 50


def test_nearest_rank_twenty_samples() -> None:
    values = list(range(1, 21))  # 1..20
    assert nearest_rank(values, 95) == 19  # ceil(19) = 19
    assert nearest_rank(values, 50) == 10


def test_nearest_rank_rejects_invalid_percentile() -> None:
    with pytest.raises(ValueError):
        nearest_rank([1], 0)


def test_ratio_without_base_is_none_not_zero_or_hundred() -> None:
    assert ratio(0, 0) is None
    assert ratio(3, 4) == 75.0


def test_incident_crossing_window_is_clipped() -> None:
    start, end = START, START + timedelta(hours=1)
    began = START - timedelta(minutes=30)
    ended = START + timedelta(minutes=10)
    assert clipped_duration(start, end, began, ended, now=end) == timedelta(minutes=10)


def test_open_incident_counts_until_now() -> None:
    start, end = START, START + timedelta(hours=1)
    now = START + timedelta(minutes=20)
    assert clipped_duration(start, end, START + timedelta(minutes=5), None, now) == timedelta(
        minutes=15
    )


def test_incident_outside_window_is_zero() -> None:
    start, end = START, START + timedelta(hours=1)
    before = START - timedelta(hours=2)
    assert clipped_duration(start, end, before, before + timedelta(minutes=5), end) == timedelta(0)
