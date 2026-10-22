"""Fórmulas das métricas (RF05). As consultas ficam em services/queries.py."""

import math
from collections.abc import Sequence
from datetime import datetime, timedelta


def nearest_rank(values: Sequence[float], percentile: float) -> float | None:
    """Percentil pelo método nearest-rank: valor na posição ceil(p/100 × n), 1-indexada.

    Devolve None quando não há amostras, para a interface mostrar "N/A".
    """
    if not 0 < percentile <= 100:
        raise ValueError("percentil deve estar em (0, 100]")
    if not values:
        return None
    ordered = sorted(values)
    rank = math.ceil(percentile / 100 * len(ordered))
    return ordered[rank - 1]


def ratio(part: int, total: int) -> float | None:
    """Proporção em porcentagem, ou None quando não há base (nunca inventa 0% ou 100%)."""
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
    """Parte de um incidente que cai dentro da janela [início, fim).

    Incidente ainda aberto conta até `now` (ou até o fim da janela, o que vier antes).
    """
    end = min(window_end, ended_at or now)
    start = max(window_start, started_at)
    return max(end - start, timedelta(0))
