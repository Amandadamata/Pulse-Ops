"""Outbox de alertas: criação dos eventos e ciclo de vida das entregas (RF06, ADR 0007)."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pulseops.db.models import (
    AlertDestination,
    AlertEvent,
    Delivery,
    DeliveryAttempt,
    Incident,
    Monitor,
)
from pulseops.db.session import SessionFactory
from pulseops.logs import redact_text


def event_key(incident_id: int, kind: str) -> str:
    return f"incident:{incident_id}:{kind.removeprefix('incident.')}"


async def enqueue_incident_alert(
    session: AsyncSession,
    *,
    kind: str,
    incident: Incident,
    monitor: Monitor,
    explanation: str,
    now: datetime,
) -> AlertEvent:
    """Cria o evento e uma entrega por destino ativo. Não faz commit: quem chama decide.

    Deve ser chamada dentro da mesma transação que mudou o incidente.
    """
    key = event_key(incident.id, kind)
    payload: dict[str, Any] = {
        "event_id": key,
        "type": kind,
        "occurred_at": now.isoformat(),
        "explanation": explanation,
        "monitor": {
            "id": monitor.id,
            "name": monitor.name,
            "url": redact_text(monitor.url),
        },
        "incident": {
            "id": incident.id,
            "status": incident.status,
            "started_at": incident.started_at.isoformat(),
            "confirmed_at": incident.confirmed_at.isoformat(),
            "ended_at": incident.ended_at.isoformat() if incident.ended_at else None,
            "failure_count": incident.failure_count,
            "failure_threshold": incident.failure_threshold,
            "recovery_threshold": incident.recovery_threshold,
            "last_outcome": incident.last_outcome,
            "last_explanation": incident.last_explanation,
        },
    }
    event = AlertEvent(
        event_key=key,
        kind=kind,
        incident_id=incident.id,
        monitor_id=monitor.id,
        payload=payload,
        created_at=now,
    )
    session.add(event)
    await session.flush()

    destinations = await session.scalars(
        select(AlertDestination).where(AlertDestination.enabled.is_(True))
    )
    for destination in destinations:
        session.add(
            Delivery(
                event_id=event.id,
                destination_id=destination.id,
                status="pending",
                attempt_count=0,
                next_attempt_at=now,
                created_at=now,
                updated_at=now,
            )
        )
    return event


def backoff_delay(attempt: int, base_seconds: float, max_seconds: float) -> float:
    """Espera antes da próxima tentativa após `attempt` falhas: base × 2^(attempt−1), com teto."""
    return float(min(base_seconds * 2 ** (attempt - 1), max_seconds))


def is_permanent_status(status_code: int) -> bool:
    """4xx indica pedido recusado pelo destino; repetir não ajuda. 408 e 429 são temporários."""
    return 400 <= status_code < 500 and status_code not in (408, 429)


@dataclass(frozen=True)
class ClaimedDelivery:
    delivery_id: int
    attempt_number: int
    url: str
    event_key: str
    payload: dict[str, Any]


async def claim_due_deliveries(
    sessions: SessionFactory, *, now: datetime, limit: int, lease_seconds: float
) -> list[ClaimedDelivery]:
    """Reserva entregas vencidas. Uma reserva vencida ('sending' antigo) volta a ser elegível,
    o que cobre o worker que morreu no meio do envio (e pode gerar duplicata: RF06.8)."""
    async with sessions.begin() as session:
        rows = (
            await session.execute(
                select(Delivery, AlertEvent, AlertDestination)
                .join(AlertEvent, AlertEvent.id == Delivery.event_id)
                .join(AlertDestination, AlertDestination.id == Delivery.destination_id)
                .where(Delivery.status.in_(("pending", "sending")), Delivery.next_attempt_at <= now)
                .order_by(Delivery.next_attempt_at, Delivery.id)
                .limit(limit)
                .with_for_update(of=Delivery, skip_locked=True)
            )
        ).all()
        claimed = []
        for delivery, event, destination in rows:
            delivery.status = "sending"
            delivery.attempt_count += 1
            delivery.next_attempt_at = now + timedelta(seconds=lease_seconds)
            delivery.updated_at = now
            claimed.append(
                ClaimedDelivery(
                    delivery_id=delivery.id,
                    attempt_number=delivery.attempt_count,
                    url=destination.url,
                    event_key=event.event_key,
                    payload=event.payload,
                )
            )
        return claimed


@dataclass(frozen=True)
class SendResult:
    ok: bool
    permanent: bool
    status_code: int | None
    duration_ms: int
    error: str | None


async def record_delivery_result(
    sessions: SessionFactory,
    claimed: ClaimedDelivery,
    result: SendResult,
    *,
    now: datetime,
    max_attempts: int,
    backoff_base: float,
    backoff_max: float,
) -> str:
    """Grava a tentativa e decide o novo estado. Devolve o status final da entrega."""
    if result.ok:
        attempt_result, status = "success", "delivered"
    elif result.permanent or claimed.attempt_number >= max_attempts:
        attempt_result, status = (
            "permanent_error" if result.permanent else "retryable_error",
            "failed",
        )
    else:
        attempt_result, status = "retryable_error", "pending"

    async with sessions.begin() as session:
        session.add(
            DeliveryAttempt(
                delivery_id=claimed.delivery_id,
                attempt_number=claimed.attempt_number,
                attempted_at=now,
                duration_ms=result.duration_ms,
                status_code=result.status_code,
                result=attempt_result,
                error=result.error,
            )
        )
        values: dict[str, Any] = {"status": status, "updated_at": now, "last_error": result.error}
        if status == "delivered":
            values["delivered_at"] = now
        elif status == "pending":
            delay = backoff_delay(claimed.attempt_number, backoff_base, backoff_max)
            values["next_attempt_at"] = now + timedelta(seconds=delay)
        # Só altera se a entrega ainda estiver reservada por esta tentativa.
        await session.execute(
            update(Delivery)
            .where(
                Delivery.id == claimed.delivery_id,
                Delivery.status == "sending",
                Delivery.attempt_count == claimed.attempt_number,
            )
            .values(**values)
        )
    return status
