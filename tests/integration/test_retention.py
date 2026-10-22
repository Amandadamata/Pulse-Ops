"""Cenário 24: retenção apaga checks antigos e preserva incidentes."""

from datetime import timedelta

from sqlalchemy import func, select

from pulseops.config import Settings
from pulseops.db.models import Check, HealthChange, Incident
from pulseops.db.session import SessionFactory
from pulseops.services.processing import purge_old_checks
from tests.support import FakeClock, ScriptedTarget
from tests.support_db import create_monitor, make_worker, tick


async def test_old_checks_are_purged_and_incidents_kept(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    monitor = await create_monitor(sessions, clock, failure_threshold=1)
    target = ScriptedTarget(clock)
    target.mode = "error"
    worker = make_worker(sessions, clock, target, settings)
    await tick(worker, clock)
    clock.advance(timedelta(days=31).total_seconds())
    target.mode = "ok"
    await tick(worker, clock)  # um check recente

    removed = await purge_old_checks(sessions, now=clock.now(), retention_days=30)
    assert removed == 1
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Check)) == 1
        incident = (await session.scalars(select(Incident))).one()
        changes = list(
            await session.scalars(select(HealthChange).where(HealthChange.monitor_id == monitor.id))
        )
    assert incident.last_check_id is None  # referência ao check apagado vira nula
    assert incident.opening_reason.startswith("Incidente confirmado")  # explicação preservada
    # A mudança "sem dados → indisponível" continua registrada; o check dela já foi apagado.
    assert [(c.to_health, c.check_id) for c in changes] == [("down", None)]


async def test_maintenance_runs_retention(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    await create_monitor(sessions, clock)
    worker = make_worker(sessions, clock, ScriptedTarget(clock), settings)
    await tick(worker, clock)
    clock.advance(timedelta(days=40).total_seconds())
    await worker.run_maintenance_once()
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Check)) == 0
