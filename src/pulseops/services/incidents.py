"""Mudanças em incidentes. Sempre chamadas dentro de uma transação aberta por quem chama."""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pulseops.db.models import Check, Incident, IncidentEvent, Monitor
from pulseops.services.alerts import enqueue_incident_alert


def _completed(check: Check) -> tuple[str, datetime]:
    if check.outcome is None or check.finished_at is None:
        raise ValueError(f"check {check.id} ainda não foi concluído")
    return check.outcome, check.finished_at


def _snapshot(monitor: Monitor) -> dict[str, Any]:
    """Valores vigentes guardados junto do evento (RF03.12)."""
    return {
        "failure_threshold": monitor.failure_threshold,
        "recovery_threshold": monitor.recovery_threshold,
        "timeout_seconds": monitor.timeout_seconds,
        "latency_threshold_ms": monitor.latency_threshold_ms,
        "config_version": monitor.config_version,
    }


async def get_open_incident(session: AsyncSession, monitor_id: int) -> Incident | None:
    return await session.scalar(
        select(Incident)
        .where(Incident.monitor_id == monitor_id, Incident.status == "open")
        .with_for_update()
    )


async def open_incident(
    session: AsyncSession,
    *,
    monitor: Monitor,
    check: Check,
    first_failure_at: datetime,
    failure_count: int,
    reason: str,
) -> Incident:
    outcome, finished_at = _completed(check)
    incident = Incident(
        monitor_id=monitor.id,
        status="open",
        started_at=first_failure_at,
        confirmed_at=finished_at,
        failure_threshold=monitor.failure_threshold,
        recovery_threshold=monitor.recovery_threshold,
        timeout_seconds=monitor.timeout_seconds,
        latency_threshold_ms=monitor.latency_threshold_ms,
        opening_reason=reason,
        failure_count=failure_count,
        last_outcome=outcome,
        last_explanation=check.explanation or "",
        last_check_id=check.id,
    )
    session.add(incident)
    await session.flush()  # gera o id; o índice único parcial é verificado aqui

    details = _snapshot(monitor)
    session.add_all(
        [
            IncidentEvent(
                incident_id=incident.id,
                kind="first_failure",
                occurred_at=first_failure_at,
                message="Primeira falha da sequência observada.",
                details=details,
            ),
            IncidentEvent(
                incident_id=incident.id,
                kind="opened",
                occurred_at=finished_at,
                message=reason,
                details={**details, "outcome": outcome, "status_code": check.status_code},
                check_id=check.id,
            ),
        ]
    )
    await enqueue_incident_alert(
        session,
        kind="incident.opened",
        incident=incident,
        monitor=monitor,
        explanation=reason,
        now=finished_at,
    )
    return incident


async def record_failure_on_open_incident(
    session: AsyncSession, *, incident: Incident, monitor: Monitor, check: Check
) -> None:
    """Novas falhas atualizam o mesmo incidente; só registra evento se o tipo de erro mudar."""
    outcome, finished_at = _completed(check)
    incident.failure_count += 1
    incident.last_check_id = check.id
    incident.last_explanation = check.explanation or ""
    if outcome != incident.last_outcome:
        session.add(
            IncidentEvent(
                incident_id=incident.id,
                kind="error_changed",
                occurred_at=finished_at,
                message=f"Tipo de falha mudou de {incident.last_outcome} para {outcome}: "
                f"{check.explanation}.",
                details={"from": incident.last_outcome, "to": outcome},
                check_id=check.id,
            )
        )
        incident.last_outcome = outcome


async def resolve_incident(
    session: AsyncSession, *, incident: Incident, monitor: Monitor, check: Check, reason: str
) -> None:
    _, finished_at = _completed(check)
    incident.status = "resolved"
    incident.ended_at = finished_at
    incident.resolution_reason = "recovered"
    incident.resolution_explanation = reason
    session.add(
        IncidentEvent(
            incident_id=incident.id,
            kind="resolved",
            occurred_at=finished_at,
            message=reason,
            details=_snapshot(monitor),
            check_id=check.id,
        )
    )
    await enqueue_incident_alert(
        session,
        kind="incident.resolved",
        incident=incident,
        monitor=monitor,
        explanation=reason,
        now=finished_at,
    )


async def close_incident_by_operator(
    session: AsyncSession, *, monitor: Monitor, action: str, now: datetime
) -> Incident | None:
    """Pausa/arquivamento encerram o incidente como 'closed' (ADR 0006)."""
    incident = await get_open_incident(session, monitor.id)
    if incident is None:
        return None
    verb = "pausado" if action == "paused" else "arquivado"
    reason = (
        f"Monitor {verb} pelo operador com o incidente aberto; o incidente foi encerrado "
        "sem recuperação observada."
    )
    incident.status = "closed"
    incident.ended_at = now
    incident.resolution_reason = f"monitor_{action}"
    incident.resolution_explanation = reason
    session.add(
        IncidentEvent(
            incident_id=incident.id,
            kind="closed",
            occurred_at=now,
            message=reason,
            details=_snapshot(monitor),
        )
    )
    await enqueue_incident_alert(
        session,
        kind="incident.closed",
        incident=incident,
        monitor=monitor,
        explanation=reason,
        now=now,
    )
    return incident


async def record_config_change(
    session: AsyncSession, *, monitor: Monitor, changed: list[str], now: datetime
) -> None:
    incident = await get_open_incident(session, monitor.id)
    if incident is None:
        return
    session.add(
        IncidentEvent(
            incident_id=incident.id,
            kind="config_changed",
            occurred_at=now,
            message="Configuração alterada com incidente aberto ("
            + ", ".join(changed)
            + "); contadores reiniciados. A recuperação passa a exigir "
            f"{monitor.recovery_threshold} sucesso(s) consecutivo(s).",
            details={**_snapshot(monitor), "changed_fields": changed},
        )
    )
