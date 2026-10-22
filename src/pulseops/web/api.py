"""API JSON em /api/v1. Todas as rotas exigem sessão (RF08.4)."""

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pulseops.db.models import AlertDestination
from pulseops.domain.outcomes import Outcome
from pulseops.security.transport import validate_destination
from pulseops.security.url_policy import UnsafeDestinationError
from pulseops.services import monitors as monitor_service
from pulseops.services import queries
from pulseops.services.errors import ConflictError, NotFoundError, ValidationFailedError
from pulseops.web.deps import ApiAuth, Db, State
from pulseops.web.schemas import (
    AlertOut,
    AttemptOut,
    CheckOut,
    CheckPage,
    DeliveryOut,
    DestinationIn,
    DestinationOut,
    DestinationPatch,
    IncidentDetailOut,
    IncidentEventOut,
    IncidentOut,
    IncidentPage,
    MetricsOut,
    MonitorIn,
    MonitorOut,
    SummaryOut,
)

router = APIRouter(prefix="/api/v1", tags=["api"])

Limit = Annotated[int, Query(ge=1, le=queries.MAX_PAGE_SIZE)]


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(404, str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(409, str(exc))
    if isinstance(exc, ValidationFailedError):
        detail = [
            {"loc": ["body", e.field], "msg": e.message, "type": "value_error"} for e in exc.errors
        ]
        return HTTPException(422, detail)
    raise exc


async def _monitor_out(
    db: Db, state: State, monitor_ids: list[int] | None = None
) -> list[MonitorOut]:
    now = state.clock.now()
    worker = await queries.worker_status(
        db, now=now, stale_after=state.settings.worker_stale_after_seconds
    )
    result = []
    for monitor in await queries.list_monitors(db, include_archived=True):
        if monitor_ids is not None and monitor.id not in monitor_ids:
            continue
        out = MonitorOut.model_validate(monitor)
        out.stale = queries.is_stale(monitor, now=now, worker=worker)
        result.append(out)
    return result


@router.get("/monitors")
async def list_monitors(
    db: Db, state: State, _: ApiAuth, include_archived: bool = False
) -> list[MonitorOut]:
    items = await _monitor_out(db, state)
    return [m for m in items if include_archived or m.state != "archived"]


@router.post("/monitors", status_code=201)
async def create_monitor(body: MonitorIn, db: Db, state: State, _: ApiAuth) -> MonitorOut:
    try:
        monitor = await monitor_service.create_monitor(
            db,
            body.to_config(),
            now=state.clock.now(),
            policy=state.policy,
            min_interval_seconds=state.settings.min_interval_seconds,
            resolver=state.resolver,
        )
    except ValidationFailedError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return (await _monitor_out(db, state, [monitor.id]))[0]


@router.get("/monitors/{monitor_id}")
async def get_monitor(monitor_id: int, db: Db, state: State, _: ApiAuth) -> MonitorOut:
    items = await _monitor_out(db, state, [monitor_id])
    if not items:
        raise HTTPException(404, f"monitor {monitor_id} não encontrado")
    return items[0]


@router.put("/monitors/{monitor_id}")
async def update_monitor(
    monitor_id: int, body: MonitorIn, db: Db, state: State, _: ApiAuth
) -> MonitorOut:
    try:
        await monitor_service.update_monitor(
            db,
            monitor_id,
            body.to_config(),
            now=state.clock.now(),
            policy=state.policy,
            min_interval_seconds=state.settings.min_interval_seconds,
            resolver=state.resolver,
        )
    except (NotFoundError, ConflictError, ValidationFailedError) as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return (await _monitor_out(db, state, [monitor_id]))[0]


@router.post("/monitors/{monitor_id}/{action}")
async def monitor_action(
    monitor_id: int, action: str, db: Db, state: State, _: ApiAuth
) -> MonitorOut:
    operations = {
        "pause": monitor_service.pause_monitor,
        "resume": monitor_service.resume_monitor,
        "archive": monitor_service.archive_monitor,
        "check": monitor_service.request_check_now,
    }
    if action not in operations:
        raise HTTPException(404, "ação desconhecida")
    try:
        await operations[action](db, monitor_id, now=state.clock.now())
    except (NotFoundError, ConflictError) as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return (await _monitor_out(db, state, [monitor_id]))[0]


@router.get("/monitors/{monitor_id}/checks")
async def list_checks(
    monitor_id: int,
    db: Db,
    _: ApiAuth,
    limit: Limit = queries.DEFAULT_PAGE_SIZE,
    cursor: str | None = None,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    outcome: Outcome | None = None,
) -> CheckPage:
    _require_aware(start, end)
    try:
        page = await queries.list_checks(
            db,
            monitor_id=monitor_id,
            limit=limit,
            cursor=cursor,
            start=start,
            end=end,
            outcome=outcome.value if outcome else None,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return CheckPage(
        items=[CheckOut.model_validate(c) for c in page.items], next_cursor=page.next_cursor
    )


@router.get("/monitors/{monitor_id}/metrics")
async def monitor_metrics(
    monitor_id: int,
    db: Db,
    state: State,
    _: ApiAuth,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
) -> MetricsOut:
    _require_aware(start, end)
    now = state.clock.now()
    end = end or now
    start = start or end - timedelta(hours=24)
    if start >= end:
        raise HTTPException(422, "'from' deve ser anterior a 'to'")
    m = await queries.monitor_metrics(db, monitor_id, start=start, end=end, now=now)
    return MetricsOut(
        start=m.start,
        end=m.end,
        evaluated_checks=m.evaluated,
        internal_errors=m.internal_errors,
        by_outcome=m.by_outcome,
        available_checks_pct=m.available_pct,
        healthy_checks_pct=m.healthy_pct,
        latency_samples=m.latency_samples,
        latency_avg_ms=m.latency_avg_ms,
        latency_p95_ms=m.latency_p95_ms,
        incident_count=m.incident_count,
        incident_duration_seconds=m.incident_duration.total_seconds(),
        last_check_at=m.last_check_at,
        gaps=[(g.gap_start, g.gap_end) for g in m.gaps],
    )


def _require_aware(*values: datetime | None) -> None:
    """Datas sem fuso seriam ambíguas; a API exige UTC explícito (por exemplo, sufixo Z)."""
    if any(v is not None and v.tzinfo is None for v in values):
        raise HTTPException(422, "datas precisam de fuso horário (use Z para UTC)")


@router.get("/incidents")
async def list_incidents(
    db: Db,
    _: ApiAuth,
    status: Annotated[str | None, Query(pattern="^(open|resolved|closed)$")] = None,
    monitor_id: int | None = None,
    limit: Limit = queries.DEFAULT_PAGE_SIZE,
    cursor: str | None = None,
) -> IncidentPage:
    try:
        page = await queries.list_incidents(
            db, status=status, monitor_id=monitor_id, limit=limit, cursor=cursor
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return IncidentPage(
        items=[IncidentOut.model_validate(i) for i, _m in page.items], next_cursor=page.next_cursor
    )


def _alert_out(view: queries.AlertView) -> AlertOut:
    return AlertOut(
        event_id=view.event.event_key,
        kind=view.event.kind,
        incident_id=view.event.incident_id,
        created_at=view.event.created_at,
        deliveries=[
            DeliveryOut(
                id=d.delivery.id,
                destination=d.destination.name,
                status=d.delivery.status,
                attempt_count=d.delivery.attempt_count,
                next_attempt_at=d.delivery.next_attempt_at,
                delivered_at=d.delivery.delivered_at,
                last_error=d.delivery.last_error,
                attempts=[AttemptOut.model_validate(a) for a in d.attempts],
            )
            for d in view.deliveries
        ],
    )


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: int, db: Db, _: ApiAuth) -> IncidentDetailOut:
    detail = await queries.incident_detail(db, incident_id)
    if detail is None:
        raise HTTPException(404, f"incidente {incident_id} não encontrado")
    return IncidentDetailOut(
        incident=IncidentOut.model_validate(detail.incident),
        events=[IncidentEventOut.model_validate(e) for e in detail.events],
        alerts=[_alert_out(a) for a in detail.alerts],
    )


@router.get("/alerts")
async def list_alerts(
    db: Db, _: ApiAuth, limit: Limit = queries.DEFAULT_PAGE_SIZE
) -> list[AlertOut]:
    return [_alert_out(a) for a in await queries.list_alerts(db, limit=limit)]


@router.get("/destinations")
async def list_destinations(db: Db, _: ApiAuth) -> list[DestinationOut]:
    rows = await db.scalars(select(AlertDestination).order_by(AlertDestination.id))
    return [DestinationOut.model_validate(d) for d in rows]


@router.post("/destinations", status_code=201)
async def create_destination(
    body: DestinationIn, db: Db, state: State, _: ApiAuth
) -> DestinationOut:
    try:
        await validate_destination(state.policy, body.url, state.resolver)
    except UnsafeDestinationError as exc:
        raise HTTPException(
            422, [{"loc": ["body", "url"], "msg": str(exc), "type": "value_error"}]
        ) from exc
    now = state.clock.now()
    destination = AlertDestination(
        name=body.name.strip(),
        url=body.url.strip(),
        enabled=body.enabled,
        created_at=now,
        updated_at=now,
    )
    db.add(destination)
    try:
        await db.commit()
    except IntegrityError as exc:
        raise HTTPException(409, "já existe um destino com este nome") from exc
    return DestinationOut.model_validate(destination)


@router.patch("/destinations/{destination_id}")
async def update_destination(
    destination_id: int, body: DestinationPatch, db: Db, state: State, _: ApiAuth
) -> DestinationOut:
    destination = await db.get(AlertDestination, destination_id)
    if destination is None:
        raise HTTPException(404, "destino não encontrado")
    destination.enabled = body.enabled
    destination.updated_at = state.clock.now()
    await db.commit()
    return DestinationOut.model_validate(destination)


@router.get("/summary")
async def get_summary(db: Db, state: State, _: ApiAuth) -> SummaryOut:
    now = state.clock.now()
    worker = await queries.worker_status(
        db, now=now, stale_after=state.settings.worker_stale_after_seconds
    )
    s = await queries.summary(db, now=now, worker=worker)
    return SummaryOut(
        total=s.total,
        by_health=s.by_health,
        stale=s.stale,
        open_incidents=s.open_incidents,
        pending_deliveries=s.pending_deliveries,
        failed_deliveries=s.failed_deliveries,
        worker_alive=worker.alive,
        worker_last_seen_at=worker.last_seen_at,
        generated_at=now,
    )
