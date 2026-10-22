"""Cenário 19: métricas sem dados e p95 com amostra pequena (RF05)."""

import random
from datetime import timedelta

import httpx

from pulseops.config import Settings
from pulseops.db.session import SessionFactory
from pulseops.domain.metrics import nearest_rank
from pulseops.services import queries
from tests.support import START, FakeClock, ScriptedTarget
from tests.support_db import create_monitor, insert_checks, make_worker, tick


async def test_no_data_returns_na_not_zero_or_hundred(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock
) -> None:
    monitor = await create_monitor(sessions, clock)
    metrics = (await api.get(f"/api/v1/monitors/{monitor.id}/metrics")).json()
    assert metrics["evaluated_checks"] == 0
    assert metrics["available_checks_pct"] is None and metrics["healthy_checks_pct"] is None
    assert metrics["latency_avg_ms"] is None and metrics["latency_p95_ms"] is None
    page = await api.get(f"/monitors/{monitor.id}")
    assert "N/A" in page.text and "Sem checks nesta janela" in page.text


async def test_formulas_and_denominators(sessions: SessionFactory, clock: FakeClock) -> None:
    monitor = await create_monitor(sessions, clock)
    await insert_checks(
        sessions,
        monitor.id,
        [
            ("healthy", 100),
            ("healthy", 300),
            ("slow", 1500),
            ("timeout", 5000),
            ("internal_error", 0),
        ],
        start=START,
    )
    async with sessions() as session:
        end = START + timedelta(hours=1)
        m = await queries.monitor_metrics(session, monitor.id, start=START, end=end, now=end)
    assert m.evaluated == 4 and m.internal_errors == 1  # erro interno fora do denominador
    assert m.available_pct == 75.0  # healthy + slow sobre 4
    assert m.healthy_pct == 50.0
    assert m.latency_samples == 3  # timeout não entra na latência
    assert m.latency_avg_ms == (100 + 300 + 1500) / 3
    assert m.latency_p95_ms == 1500  # n = 3 → p95 é o máximo


async def test_sql_percentile_matches_nearest_rank(
    sessions: SessionFactory, clock: FakeClock
) -> None:
    rng = random.Random(42)  # noqa: S311 (amostra determinística de teste, sem uso criptográfico)
    for n in (1, 2, 7, 20, 21, 137):
        monitor = await create_monitor(sessions, clock, name=f"p95 {n}")
        values = [rng.randint(10, 3000) for _ in range(n)]
        await insert_checks(sessions, monitor.id, [("healthy", v) for v in values], start=START)
        async with sessions() as session:
            m = await queries.monitor_metrics(
                session, monitor.id, start=START, end=START + timedelta(hours=1), now=START
            )
        assert m.latency_p95_ms == nearest_rank(values, 95), n


async def test_incident_crossing_window_and_open_incident_duration(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    monitor = await create_monitor(sessions, clock, failure_threshold=1)
    target = ScriptedTarget(clock)
    target.mode = "error"
    worker = make_worker(sessions, clock, target, settings)
    await tick(worker, clock, 600)  # incidente começa ~12:00 e segue aberto
    now = clock.now()
    async with sessions() as session:
        window_start = START + timedelta(minutes=5)
        m = await queries.monitor_metrics(session, monitor.id, start=window_start, end=now, now=now)
    assert m.incident_count == 1
    assert m.incident_duration == now - window_start  # cortado no início da janela


async def test_paused_period_produces_no_samples(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    monitor = await create_monitor(sessions, clock)
    worker = make_worker(sessions, clock, ScriptedTarget(clock), settings)
    await tick(worker, clock)
    await api.post(f"/api/v1/monitors/{monitor.id}/pause")
    for _ in range(5):
        await tick(worker, clock)
    metrics = (await api.get(f"/api/v1/monitors/{monitor.id}/metrics")).json()
    assert metrics["evaluated_checks"] == 1 and metrics["available_checks_pct"] == 100.0


async def test_invalid_window_is_rejected(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock
) -> None:
    monitor = await create_monitor(sessions, clock)
    params = {"from": "2026-01-15T12:00:00Z", "to": "2026-01-15T11:00:00Z"}
    assert (
        await api.get(f"/api/v1/monitors/{monitor.id}/metrics", params=params)
    ).status_code == 422
