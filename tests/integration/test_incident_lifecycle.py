"""Cenários 5 a 8 e 11 a 13 com PostgreSQL real, worker real e alvo simulado."""

from sqlalchemy import select

from pulseops.config import Settings
from pulseops.db.models import AlertEvent, CoverageGap, HealthChange, IncidentEvent
from pulseops.db.session import SessionFactory
from pulseops.services import monitors as monitor_service
from pulseops.services.processing import claim_due_runs, record_result
from tests.support import FakeClock, ScriptedTarget
from tests.support_db import (
    create_monitor,
    incidents_of,
    make_worker,
    reload,
    tick,
    update_monitor,
)


async def test_threshold_example_with_database(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    """Exemplo obrigatório do RF03 de ponta a ponta (cenários 5, 6 e 8)."""
    monitor = await create_monitor(sessions, clock)
    target = ScriptedTarget(clock)
    worker = make_worker(sessions, clock, target, settings)

    target.mode = "timeout"
    await tick(worker, clock)
    await tick(worker, clock)
    target.mode = "ok"
    await tick(worker, clock)
    assert await incidents_of(sessions, monitor.id) == []  # falha, falha, sucesso

    target.mode = "timeout"
    for _ in range(3):
        await tick(worker, clock)
    opened = await incidents_of(sessions, monitor.id)
    assert len(opened) == 1 and opened[0].status == "open"
    assert opened[0].opening_reason == (
        "Incidente confirmado após 3 falhas consecutivas; último resultado: sem resposta em 5 s."
    )
    assert opened[0].started_at < opened[0].confirmed_at  # primeira falha antes da confirmação

    for _ in range(4):  # novas falhas atualizam o mesmo incidente
        await tick(worker, clock)
    same = await incidents_of(sessions, monitor.id)
    assert len(same) == 1 and same[0].failure_count == 7

    target.mode = "ok"
    await tick(worker, clock)
    assert (await incidents_of(sessions, monitor.id))[0].status == "open"
    await tick(worker, clock)
    resolved = (await incidents_of(sessions, monitor.id))[0]
    assert resolved.status == "resolved"
    assert resolved.resolution_explanation is not None
    assert resolved.resolution_explanation.startswith("Recuperado após 2 sucessos consecutivos")

    async with sessions() as session:
        kinds = list(await session.scalars(select(AlertEvent.kind).order_by(AlertEvent.id)))
        timeline = list(
            await session.scalars(
                select(IncidentEvent.kind).order_by(IncidentEvent.occurred_at, IncidentEvent.id)
            )
        )
    assert kinds == ["incident.opened", "incident.resolved"]  # nada a cada falha repetida
    assert timeline == ["first_failure", "opened", "resolved"]


async def test_alternating_results_do_not_open_incident(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    """Cenário 7."""
    monitor = await create_monitor(sessions, clock)
    target = ScriptedTarget(clock)
    worker = make_worker(sessions, clock, target, settings)
    for mode in ["error", "error", "ok", "error", "ok", "error", "error", "ok"]:
        target.mode = mode
        await tick(worker, clock)
    assert await incidents_of(sessions, monitor.id) == []
    assert (await reload(sessions, monitor.id)).health == "healthy"


async def test_error_type_change_is_recorded_on_timeline(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    monitor = await create_monitor(sessions, clock, failure_threshold=1)
    target = ScriptedTarget(clock)
    worker = make_worker(sessions, clock, target, settings)
    target.mode = "error"
    await tick(worker, clock)
    target.mode = "refused"
    await tick(worker, clock)
    incident = (await incidents_of(sessions, monitor.id))[0]
    assert incident.last_outcome == "connection_error"
    async with sessions() as session:
        kinds = list(
            await session.scalars(
                select(IncidentEvent.kind).where(IncidentEvent.incident_id == incident.id)
            )
        )
    assert "error_changed" in kinds


async def test_pause_closes_open_incident_and_resume_starts_clean(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    """Cenário 11 e ADR 0006."""
    monitor = await create_monitor(sessions, clock, failure_threshold=2)
    target = ScriptedTarget(clock)
    worker = make_worker(sessions, clock, target, settings)
    target.mode = "error"
    await tick(worker, clock)
    await tick(worker, clock)
    assert (await incidents_of(sessions, monitor.id))[0].status == "open"

    async with sessions.begin() as session:
        await monitor_service.pause_monitor(session, monitor.id, now=clock.now())
    incident = (await incidents_of(sessions, monitor.id))[0]
    assert incident.status == "closed" and incident.resolution_reason == "monitor_paused"
    paused = await reload(sessions, monitor.id)
    assert (paused.state, paused.health, paused.consecutive_failures) == ("paused", "paused", 0)

    assert await tick(worker, clock) == 0  # pausado não é verificado

    async with sessions.begin() as session:
        await monitor_service.resume_monitor(session, monitor.id, now=clock.now())
    assert (await reload(sessions, monitor.id)).health == "no_data"
    await tick(worker, clock)  # ainda com erro: 1 falha, abaixo do limiar
    assert len(await incidents_of(sessions, monitor.id)) == 1
    await tick(worker, clock)
    incidents = await incidents_of(sessions, monitor.id)
    assert [i.status for i in incidents] == ["closed", "open"]  # novo incidente após retomar

    async with sessions() as session:
        kinds = list(await session.scalars(select(AlertEvent.kind).order_by(AlertEvent.id)))
    assert kinds == ["incident.opened", "incident.closed", "incident.opened"]


async def test_config_change_resets_counters_and_keeps_incident(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    """Cenário 12 (RF03.5)."""
    monitor = await create_monitor(sessions, clock, failure_threshold=2, recovery_threshold=1)
    target = ScriptedTarget(clock)
    worker = make_worker(sessions, clock, target, settings)
    target.mode = "error"
    await tick(worker, clock)
    await tick(worker, clock)

    await update_monitor(sessions, clock, monitor.id, recovery_threshold=3)
    changed = await reload(sessions, monitor.id)
    assert changed.config_version == 2
    assert (changed.consecutive_failures, changed.consecutive_successes) == (0, 0)
    incident = (await incidents_of(sessions, monitor.id))[0]
    assert incident.status == "open"
    assert incident.recovery_threshold == 1  # retrato da abertura não muda

    target.mode = "ok"
    for _ in range(2):
        await tick(worker, clock)
    assert (await incidents_of(sessions, monitor.id))[0].status == "open"  # agora exige 3
    await tick(worker, clock)
    assert (await incidents_of(sessions, monitor.id))[0].status == "resolved"

    async with sessions() as session:
        kinds = list(
            await session.scalars(
                select(IncidentEvent.kind).where(IncidentEvent.incident_id == incident.id)
            )
        )
    assert "config_changed" in kinds


async def test_result_of_run_started_before_config_change_does_not_count(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    monitor = await create_monitor(sessions, clock)
    target = ScriptedTarget(clock)
    target.mode = "error"
    runs = await claim_due_runs(sessions, now=clock.now(), limit=10)
    await update_monitor(sessions, clock, monitor.id, failure_threshold=1)

    observation = await target.checker().check(runs[0].target)
    assert await record_result(sessions, runs[0], observation) is True
    after = await reload(sessions, monitor.id)
    assert after.consecutive_failures == 0  # gravado no histórico, sem efeito no domínio
    assert await incidents_of(sessions, monitor.id) == []


async def test_restart_with_open_incident_continues_and_records_gap(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    """Cenário 13 e CB4: novo processo continua o mesmo incidente; atraso vira lacuna."""
    monitor = await create_monitor(sessions, clock, failure_threshold=2)
    target = ScriptedTarget(clock)
    first = make_worker(sessions, clock, target, settings)
    target.mode = "error"
    await tick(first, clock)
    await tick(first, clock)
    assert (await incidents_of(sessions, monitor.id))[0].status == "open"

    clock.advance(3600)  # worker ficou uma hora parado
    second = make_worker(sessions, clock, target, settings)
    assert await second.run_checks_once() == 1  # uma execução, não 60 atrasadas
    incidents = await incidents_of(sessions, monitor.id)
    assert len(incidents) == 1 and incidents[0].failure_count == 3

    async with sessions() as session:
        gaps = list(await session.scalars(select(CoverageGap)))
    assert len(gaps) == 1 and gaps[0].reason == "scheduler_behind"
    assert (gaps[0].gap_end - gaps[0].gap_start).total_seconds() >= 3600


async def test_every_health_change_is_explained(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    await create_monitor(sessions, clock, failure_threshold=1, recovery_threshold=1)
    target = ScriptedTarget(clock)
    worker = make_worker(sessions, clock, target, settings)
    for mode in ["ok", "slow", "error", "ok"]:
        target.mode = mode
        await tick(worker, clock)
    async with sessions() as session:
        changes = list(await session.scalars(select(HealthChange).order_by(HealthChange.id)))
    assert [(c.from_health, c.to_health) for c in changes] == [
        ("no_data", "healthy"),
        ("healthy", "degraded"),
        ("degraded", "down"),
        ("down", "healthy"),
    ]
    assert all(c.reason and c.check_id for c in changes)
