"""Latency chart: failures drawn with another shape and left out of the latency summary."""

from datetime import UTC, datetime, timedelta

from pulseops.services.queries import LatencyPoint
from pulseops.web.charts import build_latency_chart

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def point(seconds: int, duration_ms: int, outcome: str) -> LatencyPoint:
    return LatencyPoint(
        at=T0 + timedelta(seconds=seconds), duration_ms=duration_ms, outcome=outcome
    )


def test_no_points_means_no_chart() -> None:
    assert build_latency_chart([], 800) is None


def test_failures_are_flagged_and_left_out_of_latency_summary() -> None:
    chart = build_latency_chart(
        [point(0, 40, "healthy"), point(30, 2003, "timeout"), point(60, 900, "slow")], 800
    )
    assert chart is not None
    assert [d.failed for d in chart.dots] == [False, True, False]
    assert chart.summary == (
        "3 checks (1 failed); HTTP response latency: min 40 ms, max 900 ms; limit 800 ms."
    )


def test_only_failures_say_so_instead_of_inventing_latency() -> None:
    chart = build_latency_chart([point(0, 35, "connection_error")], 1000)
    assert chart is not None
    assert "no HTTP responses" in chart.summary
    assert "35 ms" not in chart.summary


def test_latency_summary_uses_the_same_responses_as_the_metrics() -> None:
    """B10: the average and p95 (RF05) count HTTP responses outside the list, like the summary."""
    chart = build_latency_chart(
        [point(0, 40, "healthy"), point(30, 120, "unexpected_status"), point(60, 2003, "timeout")],
        800,
    )
    assert chart is not None
    assert [d.failed for d in chart.dots] == [False, True, True]
    assert chart.summary == (
        "3 checks (2 failed); HTTP response latency: min 40 ms, max 120 ms; limit 800 ms."
    )
