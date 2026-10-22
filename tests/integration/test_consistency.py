"""Cenários 9, 10, 14 e 15 e restrições do banco."""

import asyncio
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from pulseops.config import Settings
from pulseops.db.models import Check, Incident
from pulseops.db.session import SessionFactory, create_engine, create_session_factory
from pulseops.services import monitors as monitor_service
from pulseops.services import processing
from pulseops.worker.__main__ import try_acquire_worker_lock
from pulseops.worker.runner import Worker
from tests.support import FakeClock, ScriptedTarget
from tests.support_db import (
    RecordingNotifier,
    count_checks,
    create_monitor,
    incidents_of,
    make_worker,
    reload,
    tick,
)


async def test_reprocessed_result_is_ignored(sessions: SessionFactory, clock: FakeClock) -> None:
    """Cenário 9: gravar duas vezes o resultado da mesma execução não duplica nada."""
    monitor = await create_monitor(sessions, clock, failure_threshold=1)
    target = ScriptedTarget(clock)
    target.mode = "error"
    [run] = await processing.claim_due_runs(sessions, now=clock.now(), limit=5)
    observation = await target.checker().check(run.target)

    assert await processing.record_result(sessions, run, observation) is True
    assert await processing.record_result(sessions, run, observation) is False
    assert await count_checks(sessions, monitor.id) == 1
    incidents = await incidents_of(sessions, monitor.id)
    assert len(incidents) == 1 and incidents[0].failure_count == 1
    assert (await reload(sessions, monitor.id)).consecutive_failures == 1


async def test_same_run_identity_cannot_be_reserved_twice(sessions: SessionFactory, clock: FakeClock) -> None:
    monitor = await create_monitor(sessions, clock)
    target = ScriptedTarget(clock)
    [run] = await processing.claim_due_runs(sessions, now=clock.now(), limit=5)
    await processing.record_result(sessions, run, await target.checker().check(run.target))

    # Simula o agendador voltando para o mesmo horário previsto (por exemplo, após restaurar backup).
    async with sessions.begin() as session:
        stored = await session.get(Check, run.check_id)
        assert stored is not None
        m = await monitor_service.get_monitor(session, monitor.id)
        m.next_run_at = stored.scheduled_at
    assert await processing.claim_due_runs(sessions, now=clock.now(), limit=5) == []
    assert await count_checks(sessions, monitor.id) == 1


async def test_overlapping_check_is_not_started(sessions: SessionFactory, clock: FakeClock) -> None:
    """Cenário 10: com um check em andamento, nem o agendador nem "verificar agora" iniciam outro."""
    monitor = await create_monitor(sessions, clock)
    [run] = await processing.claim_due_runs(sessions, now=clock.now(), limit=5)

    clock.advance(120)  # passou do próximo horário com o primeiro ainda rodando
    assert await processing.claim_due_runs(sessions, now=clock.now(), limit=5) == []
    async with sessions.begin() as session:
        await monitor_service.request_check_now(session, monitor.id, now=clock.now())
    assert await processing.claim_due_runs(sessions, now=clock.now(), limit=5) == []

    target = ScriptedTarget(clock)
    await processing.record_result(sessions, run, await target.checker().check(run.target))
    [manual] = await processing.claim_due_runs(sessions, now=clock.now(), limit=5)
    async with sessions() as session:
        stored = await session.get(Check, manual.check_id)
        assert stored is not None and stored.trigger == "manual"


async def test_database_rejects_second_running_check(sessions: SessionFactory, clock: FakeClock) -> None:
    monitor = await create_monitor(sessions, clock)
    await processing.claim_due_runs(sessions, now=clock.now(), limit=5)
    with pytest.raises(IntegrityError, match="uq_checks_one_running_per_monitor"):
        async with sessions.begin() as session:
            session.add(
                Check(
                    monitor_id=monitor.id, run_key="manual-duplicate", trigger="manual", status="running",
                    config_version=1, scheduled_at=clock.now(), started_at=clock.now(),
                )
            )


async def test_database_rejects_second_open_incident(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    monitor = await create_monitor(sessions, clock, failure_threshold=1)
    target = ScriptedTarget(clock)
    target.mode = "error"
    await tick(make_worker(sessions, clock, target, settings), clock)
    [existing] = await incidents_of(sessions, monitor.id)
    with pytest.raises(IntegrityError, match="uq_incidents_one_open_per_monitor"):
        async with sessions.begin() as session:
            session.add(
                Incident(
                    monitor_id=monitor.id, status="open", started_at=existing.started_at,
                    confirmed_at=existing.confirmed_at, failure_threshold=1, recovery_threshold=1,
                    timeout_seconds=5, latency_threshold_ms=1000, opening_reason="duplicado",
                    failure_count=1, last_outcome="timeout", last_explanation="x",
                )
            )


async def test_concurrent_claims_never_take_the_same_monitor(sessions: SessionFactory, clock: FakeClock) -> None:
    for i in range(10):
        await create_monitor(sessions, clock, name=f"monitor {i}")
    results = await asyncio.gather(
        *(processing.claim_due_runs(sessions, now=clock.now(), limit=10) for _ in range(4))
    )
    claimed = [run.monitor_id for batch in results for run in batch]
    assert len(claimed) == len(set(claimed)) == 10


async def test_interrupted_run_becomes_internal_error_not_failure(
    sessions: SessionFactory, clock: FakeClock
) -> None:
    """Falha entre a requisição e a gravação (RF03.8)."""
    monitor = await create_monitor(sessions, clock, failure_threshold=1)
    [run] = await processing.claim_due_runs(sessions, now=clock.now(), limit=5)
    clock.advance(10)
    assert await processing.mark_abandoned_runs(sessions, now=clock.now()) == 0  # ainda no prazo
    clock.advance(30)
    assert await processing.mark_abandoned_runs(sessions, now=clock.now()) == 1
    async with sessions() as session:
        stored = await session.get(Check, run.check_id)
        assert stored is not None
        assert (stored.status, stored.outcome) == ("completed", "internal_error")
    after = await reload(sessions, monitor.id)
    assert after.consecutive_failures == 0 and after.health == "no_data"
    assert await incidents_of(sessions, monitor.id) == []


async def test_database_failure_while_recording_does_not_count_as_target_failure(
    sessions: SessionFactory, clock: FakeClock, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cenário 15: o banco cai entre a requisição e a gravação."""
    monitor = await create_monitor(sessions, clock, failure_threshold=1)
    target = ScriptedTarget(clock)
    target.mode = "error"  # o alvo está mesmo com erro, mas o resultado não chega ao banco
    worker = make_worker(sessions, clock, target, settings)

    async def database_down(*args: object, **kwargs: object) -> bool:
        raise OperationalError("UPDATE checks", {}, Exception("connection refused"))

    monkeypatch.setattr(processing, "record_result", database_down)
    assert await worker.run_checks_once() == 1  # não propaga a exceção
    monkeypatch.undo()

    clock.advance(60)
    await processing.mark_abandoned_runs(sessions, now=clock.now())
    assert await count_checks(sessions, monitor.id, outcome="internal_error") == 1
    assert await incidents_of(sessions, monitor.id) == []
    assert (await reload(sessions, monitor.id)).consecutive_failures == 0

    await worker.run_checks_once()  # banco voltou: a verificação seguinte conta normalmente
    assert len(await incidents_of(sessions, monitor.id)) == 1


async def test_worker_loop_survives_unreachable_database(settings: Settings, clock: FakeClock) -> None:
    """Cenário 15: com o banco fora do ar, os laços registram o erro e continuam vivos."""
    dead = create_engine("postgresql+psycopg://pulseops:x@127.0.0.1:1/nada", pool_size=1)
    fast = settings.model_copy(update={"worker_tick_seconds": 0.01, "heartbeat_interval_seconds": 0.01})
    worker = Worker(
        sessions=create_session_factory(dead), checker=ScriptedTarget(clock).checker(),
        notifier=RecordingNotifier(), clock=clock, settings=fast,
    )
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run(stop))
    await asyncio.sleep(0.3)
    assert not task.done()  # continua tentando
    stop.set()
    await asyncio.wait_for(task, timeout=5)
    await dead.dispose()


async def test_second_worker_is_refused(engine: AsyncEngine) -> None:
    """Um único worker suportado (ADR 0002), garantido pelo banco."""
    async with engine.connect() as first, engine.connect() as second:
        assert await try_acquire_worker_lock(first) is True
        assert await try_acquire_worker_lock(second) is False
        await first.execute(text("SELECT pg_advisory_unlock_all()"))
        await first.commit()
        assert await try_acquire_worker_lock(second) is True
        await second.execute(text("SELECT pg_advisory_unlock_all()"))
        await second.commit()


async def test_stopped_worker_makes_data_stale(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    """Cenário 14: sem heartbeat recente, nada aparece como saudável."""
    monitor = await create_monitor(sessions, clock)
    target = ScriptedTarget(clock)
    worker = make_worker(sessions, clock, target, settings)
    await worker.run_maintenance_once()
    await worker.run_checks_once()

    fresh = (await api.get(f"/api/v1/monitors/{monitor.id}")).json()
    assert (fresh["health"], fresh["stale"]) == ("healthy", False)
    assert (await api.get("/api/v1/summary")).json()["worker_alive"] is True

    clock.advance(settings.worker_stale_after_seconds + 1)  # worker parou de mandar sinal
    stale = (await api.get(f"/api/v1/monitors/{monitor.id}")).json()
    assert stale["stale"] is True
    summary = (await api.get("/api/v1/summary")).json()
    assert summary["worker_alive"] is False and summary["stale"] == 1
    assert summary["by_health"].get("healthy", 0) == 0
    page = await api.get("/")
    assert "Worker sem sinal" in page.text and "Dados desatualizados" in page.text


async def test_old_last_check_is_stale_even_with_worker_alive(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    monitor = await create_monitor(sessions, clock)
    worker = make_worker(sessions, clock, ScriptedTarget(clock), settings)
    await worker.run_checks_once()
    clock.advance(2 * 60 + 5 + 31)
    await worker.heartbeat()  # worker vivo, mas este monitor não foi verificado
    assert (await api.get(f"/api/v1/monitors/{monitor.id}")).json()["stale"] is True


async def test_scheduled_time_and_observed_time_are_both_recorded(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    monitor = await create_monitor(sessions, clock)
    worker = make_worker(sessions, clock, ScriptedTarget(clock), settings)
    created_at = clock.now()
    clock.advance(1.5)  # o worker pegou a execução com 1,5 s de atraso
    await worker.run_checks_once()
    async with sessions() as session:
        check = (await session.scalars(select(Check).where(Check.monitor_id == monitor.id))).one()
    assert check.scheduled_at == created_at
    assert check.started_at - check.scheduled_at == timedelta(seconds=1.5)
    assert check.run_key == f"{monitor.id}:{created_at.isoformat(timespec='milliseconds')}"
