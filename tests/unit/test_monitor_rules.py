"""Cenário 1: configuração inválida (RF01)."""

from dataclasses import replace

import pytest

from pulseops.domain.monitor_rules import MonitorConfig, validate_config

VALID = MonitorConfig(name="API", url="https://api.example.com/health")


def fields(config: MonitorConfig, min_interval: int = 30) -> set[str]:
    return {e.field for e in validate_config(config, min_interval_seconds=min_interval)}


def test_defaults_are_valid() -> None:
    assert fields(VALID) == set()


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"name": "  "}, "name"),
        ({"name": "x" * 101}, "name"),
        ({"method": "POST"}, "method"),
        ({"interval_seconds": 10}, "interval_seconds"),
        ({"interval_seconds": 100_000}, "interval_seconds"),
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"timeout_seconds": 31, "interval_seconds": 60}, "timeout_seconds"),
        ({"failure_threshold": 0}, "failure_threshold"),
        ({"recovery_threshold": 11}, "recovery_threshold"),
        ({"accepted_status_codes": "abc"}, "accepted_status_codes"),
        ({"latency_threshold_ms": 10}, "latency_threshold_ms"),
    ],
)
def test_out_of_range_values(change: dict[str, object], field: str) -> None:
    assert field in fields(replace(VALID, **change))  # type: ignore[arg-type]


def test_timeout_must_be_smaller_than_interval() -> None:
    assert "timeout_seconds" in fields(replace(VALID, interval_seconds=30, timeout_seconds=30))


def test_latency_threshold_cannot_exceed_timeout() -> None:
    assert "latency_threshold_ms" in fields(
        replace(VALID, timeout_seconds=2, latency_threshold_ms=2001)
    )
    assert fields(replace(VALID, timeout_seconds=2, latency_threshold_ms=2000)) == set()


def test_demo_mode_allows_short_intervals() -> None:
    short = replace(VALID, interval_seconds=3, timeout_seconds=2, latency_threshold_ms=800)
    assert "interval_seconds" in fields(short, min_interval=30)
    assert fields(short, min_interval=2) == set()


def test_all_errors_reported_together() -> None:
    bad = replace(VALID, name="", method="PUT", failure_threshold=99)
    assert fields(bad) == {"name", "method", "failure_threshold"}
