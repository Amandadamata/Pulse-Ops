"""Atalhos para os testes de integração: criar monitores e rodar o worker."""

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, insert, select

from pulseops.config import Settings
from pulseops.db.models import Check, Incident, Monitor
from pulseops.db.session import SessionFactory
from pulseops.domain.monitor_rules import MonitorConfig
from pulseops.security.url_policy import DestinationPolicy
from pulseops.services import monitors
from pulseops.services.alerts import SendResult
from pulseops.worker.runner import Worker
from tests.support import FakeClock, FakeResolver, ScriptedTarget

BASE = MonitorConfig(
    name="API de pedidos",
    url="https://pedidos.example.com/health",
    interval_seconds=60,
    timeout_seconds=5,
    latency_threshold_ms=1000,
    failure_threshold=3,
    recovery_threshold=2,
)


async def create_monitor(sessions: SessionFactory, clock: FakeClock, **changes: Any) -> Monitor:
    async with sessions.begin() as session:
        return await monitors.create_monitor(
            session,
            replace(BASE, **changes),
            now=clock.now(),
            policy=DestinationPolicy(),
            min_interval_seconds=2,
            resolver=FakeResolver(),
        )


class RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.result = SendResult(True, False, 200, 5, None)

    async def send(self, url: str, event_id: str, payload: dict[str, Any]) -> SendResult:
        self.sent.append((url, event_id))
        return self.result


def make_worker(
    sessions: SessionFactory,
    clock: FakeClock,
    target: ScriptedTarget,
    settings: Settings,
    notifier: Any = None,
) -> Worker:
    return Worker(
        sessions=sessions,
        checker=target.checker(),
        notifier=notifier or RecordingNotifier(),
        clock=clock,
        settings=settings,
        worker_id="worker-de-teste",
    )


async def tick(worker: Worker, clock: FakeClock, seconds: float = 60) -> int:
    """Executa o que estiver vencido e avança o relógio um intervalo."""
    count = await worker.run_checks_once()
    clock.advance(seconds)
    return count


async def reload(sessions: SessionFactory, monitor_id: int) -> Monitor:
    async with sessions() as session:
        monitor = await session.get(Monitor, monitor_id)
        assert monitor is not None
        return monitor


async def incidents_of(sessions: SessionFactory, monitor_id: int) -> list[Incident]:
    async with sessions() as session:
        rows = await session.scalars(
            select(Incident).where(Incident.monitor_id == monitor_id).order_by(Incident.id)
        )
        return list(rows)


async def count_checks(sessions: SessionFactory, monitor_id: int, **filters: Any) -> int:
    async with sessions() as session:
        query = select(func.count()).select_from(Check).where(Check.monitor_id == monitor_id)
        for key, value in filters.items():
            query = query.where(getattr(Check, key) == value)
        return int(await session.scalar(query) or 0)


async def update_monitor(
    sessions: SessionFactory, clock: FakeClock, monitor_id: int, **changes: Any
) -> Monitor:
    async with sessions.begin() as session:
        current = monitors.config_of(await monitors.get_monitor(session, monitor_id))
        return await monitors.update_monitor(
            session,
            monitor_id,
            replace(current, **changes),
            now=clock.now(),
            policy=DestinationPolicy(),
            min_interval_seconds=2,
            resolver=FakeResolver(),
        )


async def insert_checks(
    sessions: SessionFactory,
    monitor_id: int,
    rows: list[tuple[str, int]],
    *,
    start: datetime,
    step: float = 1,
) -> None:
    """Grava checks concluídos em horários exatos (start, start+step, ...)."""
    async with sessions.begin() as session:
        for i, (outcome, ms) in enumerate(rows):
            at = start + timedelta(seconds=i * step)
            await session.execute(
                insert(Check).values(
                    monitor_id=monitor_id,
                    run_key=f"{monitor_id}:{i}",
                    trigger="scheduled",
                    status="completed",
                    config_version=1,
                    scheduled_at=at,
                    started_at=at,
                    finished_at=at,
                    duration_ms=ms,
                    status_code=200 if outcome in ("healthy", "slow") else None,
                    outcome=outcome,
                    explanation="x",
                )
            )
