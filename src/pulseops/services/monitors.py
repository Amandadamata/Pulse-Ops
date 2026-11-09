"""Monitor registration use cases (RF01)."""

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
        errors.append(FieldError("name", "a monitor with this name already exists"))

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
        health_reason="No checks yet.",
        health_changed_at=now,
        consecutive_failures=0,
        consecutive_successes=0,
        config_version=1,
        check_requested=False,
        next_run_at=now,  # first check right after registration
        created_at=now,
        updated_at=now,
    )
    session.add(monitor)
    try:
        await session.flush()
    except IntegrityError as exc:  # race between two registrations with the same name
        raise ValidationFailedError(
            [FieldError("name", "a monitor with this name already exists")]
        ) from exc
    return monitor


async def get_monitor(session: AsyncSession, monitor_id: int, *, lock: bool = False) -> Monitor:
    monitor = await session.get(Monitor, monitor_id, with_for_update=lock)
    if monitor is None:
        raise NotFoundError(f"monitor {monitor_id} not found")
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
        raise ConflictError("an archived monitor cannot be edited")
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
        # RF03.5: the configuration changed what the counters mean; counting starts over.
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
    # A new version also invalidates checks already in progress: if the monitor is
    # resumed before they finish, the result stays in the history with no effect (B6).
    monitor.config_version += 1
    monitor.consecutive_failures = 0
    monitor.consecutive_successes = 0
    monitor.first_failure_at = None


async def pause_monitor(session: AsyncSession, monitor_id: int, *, now: datetime) -> Monitor:
    monitor = await get_monitor(session, monitor_id, lock=True)
    if monitor.state != "active":
        raise ConflictError("only active monitors can be paused")
    await incidents.close_incident_by_operator(session, monitor=monitor, action="paused", now=now)
    monitor.state = "paused"
    monitor.next_run_at = None
    monitor.check_requested = False
    monitor.updated_at = now
    _reset_counters(monitor)
    _set_health(session, monitor, Health.PAUSED, "Monitor paused by the operator.", now)
    return monitor


async def resume_monitor(session: AsyncSession, monitor_id: int, *, now: datetime) -> Monitor:
    monitor = await get_monitor(session, monitor_id, lock=True)
    if monitor.state != "paused":
        raise ConflictError("only paused monitors can be resumed")
    monitor.state = "active"
    monitor.next_run_at = now
    monitor.updated_at = now
    _reset_counters(monitor)
    _set_health(
        session,
        monitor,
        Health.NO_DATA,
        "Monitor resumed; waiting for the first check.",
        now,
    )
    return monitor


async def archive_monitor(session: AsyncSession, monitor_id: int, *, now: datetime) -> Monitor:
    """Archives without deleting anything: checks, incidents and alerts stay visible (RF01.8)."""
    monitor = await get_monitor(session, monitor_id, lock=True)
    if monitor.state == "archived":
        raise ConflictError("monitor already archived")
    await incidents.close_incident_by_operator(session, monitor=monitor, action="archived", now=now)
    monitor.state = "archived"
    monitor.archived_at = now
    monitor.next_run_at = None
    monitor.check_requested = False
    monitor.updated_at = now
    _reset_counters(monitor)
    _set_health(session, monitor, Health.PAUSED, "Monitor archived by the operator.", now)
    return monitor


async def request_check_now(session: AsyncSession, monitor_id: int, *, now: datetime) -> Monitor:
    """Brings the next run forward. The reservation still goes through the same overlap
    control; if a check is already in progress, this one waits for it to finish (CB5)."""
    monitor = await get_monitor(session, monitor_id, lock=True)
    if monitor.state != "active":
        raise ConflictError("only active monitors can be checked")
    monitor.next_run_at = now
    monitor.check_requested = True
    return monitor
