"""Ciclo de uma verificação no banco: reservar → (HTTP fora daqui) → gravar resultado.

Cada função abre e fecha a própria transação curta (ADR 0003). Nenhuma delas é
chamada com uma requisição HTTP em andamento dentro da transação.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pulseops.checks.checker import CheckObservation, CheckTarget
from pulseops.db.models import Check, CoverageGap, HealthChange, Monitor
from pulseops.db.session import SessionFactory
from pulseops.domain.health import (
    Health,
    HealthTracker,
    IncidentAction,
    Observation,
    Thresholds,
    TrackerState,
)
from pulseops.domain.outcomes import Outcome
from pulseops.domain.status_codes import parse_status_codes
from pulseops.logs import log_context
from pulseops.services import incidents

logger = logging.getLogger(__name__)

# Folga além do timeout antes de considerar uma execução 'running' como interrompida.
ABANDON_GRACE = timedelta(seconds=30)


@dataclass(frozen=True)
class ClaimedRun:
    check_id: int
    monitor_id: int
    run_key: str
    config_version: int
    target: CheckTarget


def make_run_key(monitor_id: int, scheduled_at: datetime) -> str:
    return f"{monitor_id}:{scheduled_at.isoformat(timespec='milliseconds')}"


async def claim_due_runs(
    sessions: SessionFactory, *, now: datetime, limit: int
) -> list[ClaimedRun]:
    """Reserva até `limit` execuções vencidas e grava cada check como 'running'.

    `FOR UPDATE SKIP LOCKED` evita que duas transações peguem o mesmo monitor; o índice
    único parcial de check 'running' impede sobreposição mesmo se algo escapar disso.
    """
    if limit <= 0:
        return []
    running = exists().where(Check.monitor_id == Monitor.id, Check.status == "running")
    async with sessions.begin() as session:
        monitors = (
            await session.scalars(
                select(Monitor)
                .where(Monitor.state == "active", Monitor.next_run_at <= now, ~running)
                .order_by(Monitor.next_run_at, Monitor.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()

        claimed: list[ClaimedRun] = []
        for monitor in monitors:
            run = await _reserve(session, monitor, now)
            if run is not None:
                claimed.append(run)
        return claimed


async def _reserve(session: AsyncSession, monitor: Monitor, now: datetime) -> ClaimedRun | None:
    if monitor.next_run_at is None:  # o filtro da consulta já exclui; protege a tipagem
        return None
    interval = timedelta(seconds=monitor.interval_seconds)
    scheduled_at = monitor.next_run_at
    trigger = "manual" if monitor.check_requested else "scheduled"
    monitor.check_requested = False

    # Retomada sem avalanche (CB4): atrasado mais de um intervalo → agenda para agora
    # e registra o período sem checks.
    if now - scheduled_at > interval:
        session.add(
            CoverageGap(
                monitor_id=monitor.id,
                gap_start=scheduled_at,
                gap_end=now,
                reason="scheduler_behind",
            )
        )
        logger.warning(
            "lacuna de verificação registrada",
            extra={"monitor_id": monitor.id, "gap_seconds": (now - scheduled_at).total_seconds()},
        )
        scheduled_at = now

    run_key = make_run_key(monitor.id, scheduled_at)
    check_id = await session.scalar(
        insert(Check)
        .values(
            monitor_id=monitor.id,
            run_key=run_key,
            trigger=trigger,
            status="running",
            config_version=monitor.config_version,
            scheduled_at=scheduled_at,
            started_at=now,
        )
        .on_conflict_do_nothing(index_elements=["run_key"])
        .returning(Check.id)
    )
    monitor.next_run_at = max(scheduled_at + interval, now + timedelta(seconds=1))
    if check_id is None:
        # Esta execução já existe (reprocessamento da mesma identidade): não duplica.
        return None
    return ClaimedRun(
        check_id=check_id,
        monitor_id=monitor.id,
        run_key=run_key,
        config_version=monitor.config_version,
        target=CheckTarget(
            url=monitor.url,
            method=monitor.method,
            timeout_seconds=monitor.timeout_seconds,
            latency_threshold_ms=monitor.latency_threshold_ms,
            accepted=parse_status_codes(monitor.accepted_status_codes),
        ),
    )


async def record_result(
    sessions: SessionFactory, run: ClaimedRun, observation: CheckObservation
) -> bool:
    """Grava o resultado e aplica as regras de domínio em uma única transação (CB1).

    Devolve False se esta execução já tinha sido gravada (reprocessamento ignorado).
    """
    with log_context(monitor_id=run.monitor_id, run_key=run.run_key):
        async with sessions.begin() as session:
            # Trava o monitor: serializa com edição/pausa feitas ao mesmo tempo pela API.
            monitor = await session.get(Monitor, run.monitor_id, with_for_update=True)
            check = await session.get(Check, run.check_id, with_for_update=True)
            if monitor is None or check is None or check.status != "running":
                logger.info("resultado ignorado: execução já gravada")
                return False

            check.status = "completed"
            check.started_at = observation.started_at
            check.finished_at = observation.finished_at
            check.duration_ms = observation.duration_ms
            check.status_code = observation.status_code
            check.outcome = observation.outcome
            check.explanation = observation.explanation[:300]
            monitor.last_check_at = observation.finished_at

            if monitor.state != "active" or monitor.config_version != run.config_version:
                # Check iniciado antes de pausa/edição: fica no histórico, mas não decide nada.
                logger.info("resultado gravado sem efeito: monitor mudou durante a execução")
                return True

            await session.flush()
            await _apply_domain(session, monitor, check, observation)
            logger.info(
                "check gravado",
                extra={
                    "outcome": observation.outcome.value,
                    "duration_ms": observation.duration_ms,
                },
            )
            return True


async def _apply_domain(
    session: AsyncSession, monitor: Monitor, check: Check, observation: CheckObservation
) -> None:
    open_incident = await incidents.get_open_incident(session, monitor.id)
    state = TrackerState(
        health=Health(monitor.health),
        consecutive_failures=monitor.consecutive_failures,
        consecutive_successes=monitor.consecutive_successes,
        first_failure_at=monitor.first_failure_at,
        incident_open=open_incident is not None,
    )
    tracker = HealthTracker(Thresholds(monitor.failure_threshold, monitor.recovery_threshold))
    decision = tracker.apply(
        state, Observation(observation.outcome, observation.finished_at, observation.explanation)
    )

    new = decision.state
    monitor.consecutive_failures = new.consecutive_failures
    monitor.consecutive_successes = new.consecutive_successes
    monitor.first_failure_at = new.first_failure_at

    if decision.incident_action is IncidentAction.OPEN:
        incident = await incidents.open_incident(
            session,
            monitor=monitor,
            check=check,
            first_failure_at=new.first_failure_at or observation.finished_at,
            failure_count=new.consecutive_failures,
            reason=decision.reason,
        )
        logger.warning("incidente aberto", extra={"incident_id": incident.id})
    elif decision.incident_action is IncidentAction.UPDATE and open_incident is not None:
        await incidents.record_failure_on_open_incident(
            session, incident=open_incident, monitor=monitor, check=check
        )
    elif decision.incident_action is IncidentAction.RESOLVE and open_incident is not None:
        await incidents.resolve_incident(
            session, incident=open_incident, monitor=monitor, check=check, reason=decision.reason
        )
        logger.warning("incidente resolvido", extra={"incident_id": open_incident.id})

    if observation.outcome is not Outcome.INTERNAL_ERROR:
        monitor.health_reason = decision.reason
    if decision.health_changed:
        monitor.health = new.health
        monitor.health_changed_at = observation.finished_at
        session.add(
            HealthChange(
                monitor_id=monitor.id,
                changed_at=observation.finished_at,
                from_health=decision.previous_health,
                to_health=new.health,
                reason=decision.reason,
                check_id=check.id,
            )
        )


async def mark_abandoned_runs(sessions: SessionFactory, *, now: datetime) -> int:
    """Checks 'running' esquecidos (worker caiu entre a requisição e a gravação) viram
    `internal_error`. Isso não conta como falha do alvo (RF02.3, RF03.8)."""
    async with sessions.begin() as session:
        rows = (
            await session.execute(
                select(Check, Monitor.timeout_seconds)
                .join(Monitor, Monitor.id == Check.monitor_id)
                .where(Check.status == "running")
                .with_for_update(of=Check, skip_locked=True)
            )
        ).all()
        count = 0
        for check, timeout in rows:
            if now - check.started_at < timedelta(seconds=timeout) + ABANDON_GRACE:
                continue
            check.status = "completed"
            check.outcome = Outcome.INTERNAL_ERROR
            check.finished_at = now
            check.explanation = "execução interrompida antes de gravar o resultado"
            count += 1
        if count:
            logger.warning(
                "checks interrompidos marcados como erro interno", extra={"count": count}
            )
        return count


async def purge_old_checks(
    sessions: SessionFactory, *, now: datetime, retention_days: int, batch_size: int = 5000
) -> int:
    """Retenção (CB6): apaga checks concluídos antigos em lotes. Incidentes ficam."""
    cutoff = now - timedelta(days=retention_days)
    async with sessions.begin() as session:
        ids = (
            select(Check.id)
            .where(Check.started_at < cutoff, Check.status == "completed")
            .limit(batch_size)
        )
        result = await session.execute(delete(Check).where(Check.id.in_(ids.scalar_subquery())))
        return int(getattr(result, "rowcount", 0) or 0)
