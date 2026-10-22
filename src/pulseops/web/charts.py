"""Gráfico de latência em SVG, montado no servidor a partir dos checks reais (ADR 0010)."""

from dataclasses import dataclass

from pulseops.services.queries import LatencyPoint

WIDTH, HEIGHT = 720, 220
PAD_LEFT, PAD_RIGHT, PAD_TOP, PAD_BOTTOM = 56, 12, 12, 28
ANSWERED = ("healthy", "slow")  # resultados com status aceito


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
            failed=p.outcome not in ANSWERED,
        )
        for i, p in enumerate(points)
    ]
    ticks = [(y_of(top_value * f), f"{top_value * f:.0f} ms") for f in (0, 0.25, 0.5, 0.75)]
    # A latência, como nas métricas, só considera checks com status aceito; a duração
    # de uma falha (até o timeout, por exemplo) aparece no gráfico, mas não no resumo.
    answered = [p.duration_ms for p in points if p.outcome in ANSWERED]
    failures = len(points) - len(answered)
    latency = (
        f"latência mínima {min(answered)} ms, máxima {max(answered)} ms"
        if answered
        else "nenhum check com status aceito"
    )
    summary = f"{len(points)} checks ({failures} com falha); {latency}; limite {threshold_ms} ms."
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
