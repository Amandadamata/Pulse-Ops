"""Consultas de leitura: histórico (RF04), métricas (RF05) e estado do worker (RF09)."""

import base64
import binascii
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from pulseops.db.models import (
    AlertDestination,
    AlertEvent,
    Check,
    CoverageGap,
    Delivery,
    DeliveryAttempt,
    HealthChange,
    Incident,
    IncidentEvent,
    Monitor,
    WorkerHeartbeat,
)
from pulseops.domain.metrics import clipped_duration, ratio

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50
STALE_GRACE = timedelta(seconds=30)


# ---- paginação por cursor ----------------------------------------------------------


def encode_cursor(moment: datetime, row_id: int) -> str:
    raw = f"{moment.isoformat()}|{row_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        moment_text, id_text = base64.urlsafe_b64decode(padded).decode().split("|")
        moment = datetime.fromisoformat(moment_text)
        if moment.tzinfo is None:
            raise ValueError("cursor sem fuso")
        return moment, int(id_text)
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise ValueError("cursor inválido") from exc


@dataclass
class Page[T]:
    items: list[T]
    next_cursor: str | None


# ---- worker e "dados desatualizados" ----------------------------------------------


@dataclass(frozen=True)
class WorkerStatus:
    last_seen_at: datetime | None
    age_seconds: float | None
    alive: bool


async def worker_status(session: AsyncSession, *, now: datetime, stale_after: int) -> WorkerStatus:
    last_seen = await session.scalar(select(func.max(WorkerHeartbeat.last_seen_at)))
    if last_seen is None:
        return WorkerStatus(None, None, False)
    age = (now - last_seen).total_seconds()
    return WorkerStatus(last_seen, age, age <= stale_after)


def is_stale(monitor: Monitor, *, now: datetime, worker: WorkerStatus) -> bool:
    """Dados desatualizados (RF03): worker sem sinal ou último check velho demais."""
    if monitor.state != "active":
        return False
    if not worker.alive:
        return True
    reference = monitor.last_check_at or monitor.updated_at
    limit = timedelta(seconds=2 * monitor.interval_seconds + monitor.timeout_seconds) + STALE_GRACE
    return now - reference > limit


# ---- monitores e resumo -------------------------------------------------------------


async def list_monitors(session: AsyncSession, *, include_archived: bool = False) -> list[Monitor]:
    query = select(Monitor).order_by(func.lower(Monitor.name), Monitor.id)
    if not include_archived:
        query = query.where(Monitor.state != "archived")
    return list((await session.scalars(query)).all())


@dataclass
class Summary:
    total: int = 0
    by_health: dict[str, int] = field(default_factory=dict)
    stale: int = 0
    open_incidents: int = 0
    pending_deliveries: int = 0
    failed_deliveries: int = 0


async def summary(session: AsyncSession, *, now: datetime, worker: WorkerStatus) -> Summary:
    result = Summary()
    for monitor in await list_monitors(session):
        result.total += 1
        if is_stale(monitor, now=now, worker=worker):
            result.stale += 1
            continue
        result.by_health[monitor.health] = result.by_health.get(monitor.health, 0) + 1
    result.open_incidents = int(
        await session.scalar(select(func.count()).where(Incident.status == "open")) or 0
    )
    rows = await session.execute(select(Delivery.status, func.count()).group_by(Delivery.status))
    counts: dict[str, int] = {status: count for status, count in rows.tuples()}
    result.pending_deliveries = counts.get("pending", 0) + counts.get("sending", 0)
    result.failed_deliveries = counts.get("failed", 0)
    return result


# ---- histórico -----------------------------------------------------------------------


async def list_checks(
    session: AsyncSession,
    *,
    monitor_id: int,
    limit: int = DEFAULT_PAGE_SIZE,
    cursor: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    outcome: str | None = None,
) -> Page[Check]:
    """Checks concluídos, mais recentes primeiro, ordem estável (started_at, id)."""
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    query = select(Check).where(Check.monitor_id == monitor_id, Check.status == "completed")
    if start is not None:
        query = query.where(Check.started_at >= start)
    if end is not None:
        query = query.where(Check.started_at < end)
    if outcome is not None:
        query = query.where(Check.outcome == outcome)
    if cursor:
        moment, row_id = decode_cursor(cursor)
        query = query.where(tuple_(Check.started_at, Check.id) < tuple_(moment, row_id))
    query = query.order_by(Check.started_at.desc(), Check.id.desc()).limit(limit + 1)
    return _page(list((await session.scalars(query)).all()), limit, lambda c: (c.started_at, c.id))


async def list_incidents(
    session: AsyncSession,
    *,
    status: str | None = None,
    monitor_id: int | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    cursor: str | None = None,
) -> Page[tuple[Incident, Monitor]]:
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    query: Select[Incident, Monitor] = select(Incident, Monitor).join(
        Monitor, Monitor.id == Incident.monitor_id
    )
    if status == "closed":  # "encerrados" na interface = resolvidos ou fechados
        query = query.where(Incident.status != "open")
    elif status is not None:
        query = query.where(Incident.status == status)
    if monitor_id is not None:
        query = query.where(Incident.monitor_id == monitor_id)
    if cursor:
        moment, row_id = decode_cursor(cursor)
        query = query.where(tuple_(Incident.confirmed_at, Incident.id) < tuple_(moment, row_id))
    query = query.order_by(Incident.confirmed_at.desc(), Incident.id.desc()).limit(limit + 1)
    rows = [(r[0], r[1]) for r in (await session.execute(query)).all()]
    return _page(rows, limit, lambda r: (r[0].confirmed_at, r[0].id))


def _page[T](rows: list[T], limit: int, key: Any) -> Page[T]:
    if len(rows) > limit:
        rows = rows[:limit]
        moment, row_id = key(rows[-1])
        return Page(rows, encode_cursor(moment, row_id))
    return Page(rows, None)


@dataclass
class DeliveryView:
    delivery: Delivery
    destination: AlertDestination
    attempts: list[DeliveryAttempt]


@dataclass
class AlertView:
    event: AlertEvent
    deliveries: list[DeliveryView]


@dataclass
class IncidentDetail:
    incident: Incident
    monitor: Monitor
    events: list[IncidentEvent]
    alerts: list[AlertView]


async def incident_detail(session: AsyncSession, incident_id: int) -> IncidentDetail | None:
    row = (
        await session.execute(
            select(Incident, Monitor)
            .join(Monitor, Monitor.id == Incident.monitor_id)
            .where(Incident.id == incident_id)
        )
    ).first()
    if row is None:
        return None
    events = (
        await session.scalars(
            select(IncidentEvent)
            .where(IncidentEvent.incident_id == incident_id)
            .order_by(IncidentEvent.occurred_at, IncidentEvent.id)
        )
    ).all()
    alert_events = (
        await session.scalars(
            select(AlertEvent)
            .where(AlertEvent.incident_id == incident_id)
            .order_by(AlertEvent.created_at, AlertEvent.id)
        )
    ).all()
    return IncidentDetail(
        row[0], row[1], list(events), await _alert_views(session, list(alert_events))
    )


async def list_alerts(session: AsyncSession, *, limit: int = DEFAULT_PAGE_SIZE) -> list[AlertView]:
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    events = (
        await session.scalars(
            select(AlertEvent)
            .order_by(AlertEvent.created_at.desc(), AlertEvent.id.desc())
            .limit(limit)
        )
    ).all()
    return await _alert_views(session, list(events))


async def _alert_views(session: AsyncSession, events: list[AlertEvent]) -> list[AlertView]:
    if not events:
        return []
    rows = (
        await session.execute(
            select(Delivery, AlertDestination)
            .join(AlertDestination, AlertDestination.id == Delivery.destination_id)
            .where(Delivery.event_id.in_([e.id for e in events]))
            .order_by(Delivery.id)
        )
    ).all()
    attempts = (
        await session.scalars(
            select(DeliveryAttempt)
            .where(DeliveryAttempt.delivery_id.in_([r[0].id for r in rows] or [0]))
            .order_by(DeliveryAttempt.delivery_id, DeliveryAttempt.attempt_number)
        )
    ).all()
    by_delivery: dict[int, list[DeliveryAttempt]] = {}
    for attempt in attempts:
        by_delivery.setdefault(attempt.delivery_id, []).append(attempt)
    by_event: dict[int, list[DeliveryView]] = {}
    for delivery, destination in rows:
        view = DeliveryView(delivery, destination, by_delivery.get(delivery.id, []))
        by_event.setdefault(delivery.event_id, []).append(view)
    return [AlertView(e, by_event.get(e.id, [])) for e in events]


async def health_changes(
    session: AsyncSession, monitor_id: int, *, limit: int = 20
) -> list[HealthChange]:
    return list(
        (
            await session.scalars(
                select(HealthChange)
                .where(HealthChange.monitor_id == monitor_id)
                .order_by(HealthChange.changed_at.desc(), HealthChange.id.desc())
                .limit(limit)
            )
        ).all()
    )


# ---- métricas ------------------------------------------------------------------------

RESPONSE_OUTCOMES = ("healthy", "slow", "unexpected_status")


@dataclass
class Metrics:
    start: datetime
    end: datetime
    evaluated: int  # N: checks na janela, sem erros internos
    internal_errors: int
    by_outcome: dict[str, int]
    available_pct: float | None
    healthy_pct: float | None
    latency_samples: int
    latency_avg_ms: float | None
    latency_p95_ms: float | None
    incident_count: int
    incident_duration: timedelta
    last_check_at: datetime | None
    gaps: list[CoverageGap]


async def monitor_metrics(
    session: AsyncSession, monitor_id: int, *, start: datetime, end: datetime, now: datetime
) -> Metrics:
    """Fórmulas em docs/requisitos.md (RF05). Janela [start, end)."""
    in_window = (
        Check.monitor_id == monitor_id,
        Check.status == "completed",
        Check.started_at >= start,
        Check.started_at < end,
    )
    rows = await session.execute(
        select(Check.outcome, func.count()).where(*in_window).group_by(Check.outcome)
    )
    by_outcome: dict[str, int] = {outcome or "": count for outcome, count in rows.tuples()}
    internal = by_outcome.get("internal_error", 0)
    evaluated = sum(by_outcome.values()) - internal
    available = by_outcome.get("healthy", 0) + by_outcome.get("slow", 0)

    # percentile_disc(0.95) devolve o primeiro valor com distribuição acumulada >= 0,95:
    # é o mesmo resultado do nearest-rank (ADR 0011).
    latency = (
        await session.execute(
            select(
                func.count(Check.duration_ms),
                func.avg(Check.duration_ms),
                func.percentile_disc(0.95).within_group(Check.duration_ms),
            ).where(*in_window, Check.outcome.in_(RESPONSE_OUTCOMES))
        )
    ).one()
    samples = int(latency[0])

    incidents = (
        await session.scalars(
            select(Incident).where(
                Incident.monitor_id == monitor_id,
                Incident.started_at < end,
                (Incident.ended_at.is_(None)) | (Incident.ended_at > start),
            )
        )
    ).all()
    duration = sum(
        (clipped_duration(start, end, i.started_at, i.ended_at, now) for i in incidents),
        timedelta(0),
    )

    last_check_at = await session.scalar(
        select(func.max(Check.finished_at)).where(
            Check.monitor_id == monitor_id, Check.status == "completed"
        )
    )
    gaps = (
        await session.scalars(
            select(CoverageGap)
            .where(
                CoverageGap.monitor_id == monitor_id,
                CoverageGap.gap_start < end,
                CoverageGap.gap_end > start,
            )
            .order_by(CoverageGap.gap_start)
        )
    ).all()

    return Metrics(
        start=start,
        end=end,
        evaluated=evaluated,
        internal_errors=internal,
        by_outcome=by_outcome,
        available_pct=ratio(available, evaluated),
        healthy_pct=ratio(by_outcome.get("healthy", 0), evaluated),
        latency_samples=samples,
        latency_avg_ms=float(latency[1]) if samples else None,
        latency_p95_ms=float(latency[2]) if samples else None,
        incident_count=len(incidents),
        incident_duration=duration,
        last_check_at=last_check_at,
        gaps=list(gaps),
    )


@dataclass(frozen=True)
class LatencyPoint:
    at: datetime
    duration_ms: int
    outcome: str


async def latency_series(
    session: AsyncSession, monitor_id: int, *, start: datetime, end: datetime, limit: int = 300
) -> list[LatencyPoint]:
    """Pontos do gráfico: os `limit` checks mais recentes da janela, em ordem cronológica."""
    rows = (
        await session.execute(
            select(Check.started_at, Check.duration_ms, Check.outcome)
            .where(
                Check.monitor_id == monitor_id,
                Check.status == "completed",
                Check.started_at >= start,
                Check.started_at < end,
                Check.outcome != "internal_error",
            )
            .order_by(Check.started_at.desc(), Check.id.desc())
            .limit(limit)
        )
    ).all()
    return [LatencyPoint(r[0], r[1] or 0, r[2] or "") for r in reversed(rows)]
