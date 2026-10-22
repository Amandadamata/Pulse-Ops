"""Casos de uso do cadastro de monitores (RF01)."""

from dataclasses import asdict
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pulseops.db.models import HealthChange, Monitor
from pulseops.domain.health import Health
from pulseops.domain.monitor_rules import CHECK_FIELDS, FieldError, MonitorConfig, validate_config
from pulseops.security.transport import Resolver, validate_destination
from pulseops.security.url_policy import DestinationPolicy, UnsafeDestinationError
from pulseops.services import incidents
from pulseops.services.errors import ConflictError, NotFoundError, ValidationFailedError


async def _validate(
    session: AsyncSession,
    config: MonitorConfig,
    *,
    policy: DestinationPolicy,
    min_interval_seconds: int,
    resolver: Resolver | None,
    exclude_id: int | None = None,
) -> None:
    errors = validate_config(config, min_interval_seconds=min_interval_seconds)
    if not any(e.field == "url" for e in errors):
        try:
            await validate_destination(policy, config.url, resolver)
        except UnsafeDestinationError as exc:
            errors.append(FieldError("url", str(exc)))

    duplicate = select(Monitor.id).where(
        func.lower(Monitor.name) == config.name.strip().lower(), Monitor.state != "archived"
    )
    if exclude_id is not None:
        duplicate = duplicate.where(Monitor.id != exclude_id)
    if await session.scalar(duplicate):
        errors.append(FieldError("name", "já existe um monitor com este nome"))

    if errors:
        raise ValidationFailedError(errors)


async def create_monitor(
    session: AsyncSession,
    config: MonitorConfig,
    *,
    now: datetime,
    policy: DestinationPolicy,
    min_interval_seconds: int,
    resolver: Resolver | None = None,
) -> Monitor:
    await _validate(
        session, config, policy=policy, min_interval_seconds=min_interval_seconds, resolver=resolver
    )
    values = asdict(config)
    values["name"] = config.name.strip()
    values["url"] = config.url.strip()
    monitor = Monitor(
        **values,
        state="active",
        health=Health.NO_DATA,
        health_reason="Ainda sem verificações.",
        health_changed_at=now,
        consecutive_failures=0,
        consecutive_successes=0,
        config_version=1,
        check_requested=False,
        next_run_at=now,  # primeira verificação logo após o cadastro
        created_at=now,
        updated_at=now,
    )
    session.add(monitor)
    try:
        await session.flush()
    except IntegrityError as exc:  # corrida entre dois cadastros com o mesmo nome
        raise ValidationFailedError(
            [FieldError("name", "já existe um monitor com este nome")]
        ) from exc
    return monitor


async def get_monitor(session: AsyncSession, monitor_id: int, *, lock: bool = False) -> Monitor:
    monitor = await session.get(Monitor, monitor_id, with_for_update=lock)
    if monitor is None:
        raise NotFoundError(f"monitor {monitor_id} não encontrado")
    return monitor


def config_of(monitor: Monitor) -> MonitorConfig:
    return MonitorConfig(
        name=monitor.name,
        url=monitor.url,
        method=monitor.method,
        interval_seconds=monitor.interval_seconds,
        timeout_seconds=monitor.timeout_seconds,
        accepted_status_codes=monitor.accepted_status_codes,
        latency_threshold_ms=monitor.latency_threshold_ms,
        failure_threshold=monitor.failure_threshold,
        recovery_threshold=monitor.recovery_threshold,
        description=monitor.description,
    )


async def update_monitor(
    session: AsyncSession,
    monitor_id: int,
    config: MonitorConfig,
    *,
    now: datetime,
    policy: DestinationPolicy,
    min_interval_seconds: int,
    resolver: Resolver | None = None,
) -> Monitor:
    monitor = await get_monitor(session, monitor_id, lock=True)
    if monitor.state == "archived":
        raise ConflictError("monitor arquivado não pode ser editado")
    await _validate(
        session,
        config,
        policy=policy,
        min_interval_seconds=min_interval_seconds,
        resolver=resolver,
        exclude_id=monitor.id,
    )

    before = asdict(config_of(monitor))
    after = asdict(config)
    after["name"] = config.name.strip()
    after["url"] = config.url.strip()
    changed_check_fields = [f for f in CHECK_FIELDS if before[f] != after[f]]
    for field, value in after.items():
        setattr(monitor, field, value)
    monitor.updated_at = now

    if changed_check_fields:
        # RF03.5: a configuração mudou o significado dos contadores; recomeça a contagem.
        monitor.config_version += 1
        monitor.consecutive_failures = 0
        monitor.consecutive_successes = 0
        monitor.first_failure_at = None
        await incidents.record_config_change(
            session, monitor=monitor, changed=changed_check_fields, now=now
        )
    if before["interval_seconds"] != after["interval_seconds"] and monitor.state == "active":
        monitor.next_run_at = now
    return monitor


def _set_health(
    session: AsyncSession, monitor: Monitor, health: Health, reason: str, now: datetime
) -> None:
    if monitor.health != health:
        session.add(
            HealthChange(
                monitor_id=monitor.id,
                changed_at=now,
                from_health=monitor.health,
                to_health=health,
                reason=reason,
            )
        )
        monitor.health = health
        monitor.health_changed_at = now
    monitor.health_reason = reason


def _reset_counters(monitor: Monitor) -> None:
    # Nova versão também invalida checks que já estavam em andamento: se o monitor for
    # retomado antes de eles terminarem, o resultado fica no histórico sem efeito (B6).
    monitor.config_version += 1
    monitor.consecutive_failures = 0
    monitor.consecutive_successes = 0
    monitor.first_failure_at = None


async def pause_monitor(session: AsyncSession, monitor_id: int, *, now: datetime) -> Monitor:
    monitor = await get_monitor(session, monitor_id, lock=True)
    if monitor.state != "active":
        raise ConflictError("apenas monitores ativos podem ser pausados")
    await incidents.close_incident_by_operator(session, monitor=monitor, action="paused", now=now)
    monitor.state = "paused"
    monitor.next_run_at = None
    monitor.check_requested = False
    monitor.updated_at = now
    _reset_counters(monitor)
    _set_health(session, monitor, Health.PAUSED, "Monitor pausado pelo operador.", now)
    return monitor


async def resume_monitor(session: AsyncSession, monitor_id: int, *, now: datetime) -> Monitor:
    monitor = await get_monitor(session, monitor_id, lock=True)
    if monitor.state != "paused":
        raise ConflictError("apenas monitores pausados podem ser retomados")
    monitor.state = "active"
    monitor.next_run_at = now
    monitor.updated_at = now
    _reset_counters(monitor)
    _set_health(
        session,
        monitor,
        Health.NO_DATA,
        "Monitor retomado; aguardando a primeira verificação.",
        now,
    )
    return monitor


async def archive_monitor(session: AsyncSession, monitor_id: int, *, now: datetime) -> Monitor:
    """Arquiva sem apagar nada: checks, incidentes e alertas continuam consultáveis (RF01.8)."""
    monitor = await get_monitor(session, monitor_id, lock=True)
    if monitor.state == "archived":
        raise ConflictError("monitor já arquivado")
    await incidents.close_incident_by_operator(session, monitor=monitor, action="archived", now=now)
    monitor.state = "archived"
    monitor.archived_at = now
    monitor.next_run_at = None
    monitor.check_requested = False
    monitor.updated_at = now
    _reset_counters(monitor)
    _set_health(session, monitor, Health.PAUSED, "Monitor arquivado pelo operador.", now)
    return monitor


async def request_check_now(session: AsyncSession, monitor_id: int, *, now: datetime) -> Monitor:
    """Antecipa a próxima execução. A reserva continua passando pelo mesmo controle de
    sobreposição; se já houver um check em andamento, este espera ele terminar (CB5)."""
    monitor = await get_monitor(session, monitor_id, lock=True)
    if monitor.state != "active":
        raise ConflictError("apenas monitores ativos podem ser verificados")
    monitor.next_run_at = now
    monitor.check_requested = True
    return monitor
