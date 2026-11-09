"""Latency chart in SVG, built on the server from real checks (ADR 0010)."""

from dataclasses import dataclass

from pulseops.services.queries import RESPONSE_OUTCOMES, LatencyPoint

WIDTH, HEIGHT = 720, 220
PAD_LEFT, PAD_RIGHT, PAD_TOP, PAD_BOTTOM = 56, 12, 12, 28
ACCEPTED = ("healthy", "slow")  # accepted status; anything else is drawn as a failure


@dataclass(frozen=True)
class ChartDot:
    x: float
    y: float
    outcome: str
    label: str
    failed: bool


@dataclass(frozen=True)
class LatencyChart:
    width: int
    height: int
    polyline: str
    dots: list[ChartDot]
    threshold_y: float
    y_ticks: list[tuple[float, str]]
    plot_left: int
    plot_right: int
    plot_bottom: int
    summary: str


def build_latency_chart(points: list[LatencyPoint], threshold_ms: int) -> LatencyChart | None:
    if not points:
        return None
    top_value = max(max(p.duration_ms for p in points), threshold_ms) * 1.15
    plot_w = WIDTH - PAD_LEFT - PAD_RIGHT
    plot_h = HEIGHT - PAD_TOP - PAD_BOTTOM
    bottom = PAD_TOP + plot_h

    def y_of(value: float) -> float:
        return round(bottom - value / top_value * plot_h, 1)

    step = plot_w / max(len(points) - 1, 1)
    dots = [
        ChartDot(
            x=round(PAD_LEFT + i * step, 1),
            y=y_of(p.duration_ms),
            outcome=p.outcome,
            label=f"{p.at.isoformat(timespec='seconds')} — {p.duration_ms} ms ({p.outcome})",
            failed=p.outcome not in ACCEPTED,
        )
        for i, p in enumerate(points)
    ]
    ticks = [(y_of(top_value * f), f"{top_value * f:.0f} ms") for f in (0, 0.25, 0.5, 0.75)]
    # Same base as the average latency and p95 (RF05): checks that got an HTTP response,
    # including a status outside the list. Timeouts and connection errors stay out of the summary,
    # because their duration measures the deadline or the failure, not the response (B9, B10).
    responses = [p.duration_ms for p in points if p.outcome in RESPONSE_OUTCOMES]
    failures = sum(1 for d in dots if d.failed)
    latency = (
        f"HTTP response latency: min {min(responses)} ms, max {max(responses)} ms"
        if responses
        else "no HTTP responses"
    )
    summary = f"{len(points)} checks ({failures} failed); {latency}; limit {threshold_ms} ms."
    return LatencyChart(
        width=WIDTH,
        height=HEIGHT,
        polyline=" ".join(f"{d.x},{d.y}" for d in dots),
        dots=dots,
        threshold_y=y_of(threshold_ms),
        y_ticks=ticks,
        plot_left=PAD_LEFT,
        plot_right=WIDTH - PAD_RIGHT,
        plot_bottom=bottom,
        summary=summary,
    )
