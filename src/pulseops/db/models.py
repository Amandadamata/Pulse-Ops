"""Tabelas do PulseOps (SQLAlchemy 2.x, estilo `Mapped[...]`).

Restrições que protegem regras de negócio ficam aqui e na migração, para que o
banco garanta o que a aplicação promete (por exemplo, um incidente aberto por
monitor), mesmo que exista um bug no código Python.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Nomes previsíveis para constraints: facilitam migrações e mensagens de erro.
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Timestamp = DateTime(timezone=True)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class Operator(Base):
    __tablename__ = "operators"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class OperatorSession(Base):
    __tablename__ = "operator_sessions"

    # SHA-256 do token do cookie, em hexadecimal. O token em si nunca é gravado.
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("operators.id", ondelete="CASCADE"))
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    expires_at: Mapped[datetime] = mapped_column(Timestamp, index=True)


class Monitor(Base):
    __tablename__ = "monitors"
    __table_args__ = (
        CheckConstraint("method IN ('GET', 'HEAD')", name="method"),
        CheckConstraint("state IN ('active', 'paused', 'archived')", name="state"),
        CheckConstraint(
            "health IN ('no_data', 'healthy', 'degraded', 'down', 'paused')", name="health"
        ),
        # Limites absolutos. O mínimo de 30 s do modo normal é validado na aplicação,
        # porque o modo demonstração permite 2 s.
        CheckConstraint("interval_seconds BETWEEN 2 AND 86400", name="interval"),
        CheckConstraint("timeout_seconds BETWEEN 1 AND 30", name="timeout"),
        CheckConstraint("timeout_seconds < interval_seconds", name="timeout_lt_interval"),
        CheckConstraint(
            "latency_threshold_ms BETWEEN 50 AND timeout_seconds * 1000", name="latency"
        ),
        CheckConstraint("failure_threshold BETWEEN 1 AND 10", name="failure_threshold"),
        CheckConstraint("recovery_threshold BETWEEN 1 AND 10", name="recovery_threshold"),
        CheckConstraint(
            "consecutive_failures >= 0 AND consecutive_successes >= 0", name="counters"
        ),
        CheckConstraint("(state = 'archived') = (archived_at IS NOT NULL)", name="archived_at"),
        # Nome único entre monitores não arquivados, sem diferenciar maiúsculas (RF01.7).
        Index(
            "uq_monitors_active_name",
            func.lower(text("name")),
            unique=True,
            postgresql_where=text("state <> 'archived'"),
        ),
        # Consulta do agendador: monitores ativos com next_run_at vencido.
        Index(
            "ix_monitors_due",
            "next_run_at",
            postgresql_where=text("state = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), default="")
    url: Mapped[str] = mapped_column(String(2048))
    method: Mapped[str] = mapped_column(String(4), default="GET")
    interval_seconds: Mapped[int] = mapped_column(Integer)
    timeout_seconds: Mapped[int] = mapped_column(Integer)
    accepted_status_codes: Mapped[str] = mapped_column(String(100))
    latency_threshold_ms: Mapped[int] = mapped_column(Integer)
    failure_threshold: Mapped[int] = mapped_column(Integer)
    recovery_threshold: Mapped[int] = mapped_column(Integer)

    state: Mapped[str] = mapped_column(String(10), default="active")
    health: Mapped[str] = mapped_column(String(10), default="no_data")
    health_reason: Mapped[str] = mapped_column(Text, default="Ainda sem verificações.")
    health_changed_at: Mapped[datetime] = mapped_column(Timestamp)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_successes: Mapped[int] = mapped_column(Integer, default=0)
    first_failure_at: Mapped[datetime | None] = mapped_column(Timestamp)
    config_version: Mapped[int] = mapped_column(Integer, default=1)

    next_run_at: Mapped[datetime | None] = mapped_column(Timestamp)
    # "Verificar agora" pedido pelo operador; o próximo check é marcado como manual (CB5).
    check_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    last_check_at: Mapped[datetime | None] = mapped_column(Timestamp)
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    updated_at: Mapped[datetime] = mapped_column(Timestamp)
    archived_at: Mapped[datetime | None] = mapped_column(Timestamp)


class Check(Base):
    __tablename__ = "checks"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'completed')", name="status"),
        CheckConstraint("trigger IN ('scheduled', 'manual')", name="trigger"),
        CheckConstraint(
            "outcome IN ('healthy', 'slow', 'unexpected_status', 'timeout', "
            "'connection_error', 'tls_error', 'blocked', 'internal_error')",
            name="outcome",
        ),
        CheckConstraint(
            "(status = 'running' AND outcome IS NULL AND finished_at IS NULL) OR "
            "(status = 'completed' AND outcome IS NOT NULL AND finished_at IS NOT NULL)",
            name="completed_has_outcome",
        ),
        # No máximo um check em andamento por monitor: o banco impede sobreposição (CB3).
        Index(
            "uq_checks_one_running_per_monitor",
            "monitor_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
        # Histórico de um monitor, mais recente primeiro, com desempate por id (RF04.1).
        Index("ix_checks_monitor_history", "monitor_id", "started_at", "id"),
        # Retenção: apagar checks antigos de todos os monitores (CB6).
        Index("ix_checks_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id", ondelete="RESTRICT"))
    # Identidade da execução agendada: "{monitor_id}:{scheduled_at ISO UTC}".
    run_key: Mapped[str] = mapped_column(String(80), unique=True)
    trigger: Mapped[str] = mapped_column(String(10), default="scheduled")
    status: Mapped[str] = mapped_column(String(10), default="running")
    config_version: Mapped[int] = mapped_column(Integer)
    scheduled_at: Mapped[datetime] = mapped_column(Timestamp)
    started_at: Mapped[datetime] = mapped_column(Timestamp)
    finished_at: Mapped[datetime | None] = mapped_column(Timestamp)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    status_code: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str | None] = mapped_column(String(20))
    explanation: Mapped[str | None] = mapped_column(String(300))


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'resolved', 'closed')", name="status"),
        CheckConstraint("(status = 'open') = (ended_at IS NULL)", name="ended_when_not_open"),
        CheckConstraint("started_at <= confirmed_at", name="started_before_confirmed"),
        # Um incidente aberto por monitor, garantido pelo banco (RF03.11).
        Index(
            "uq_incidents_one_open_per_monitor",
            "monitor_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        # Lista de incidentes (geral e por monitor), mais recentes primeiro.
        Index("ix_incidents_confirmed", "confirmed_at", "id"),
        Index("ix_incidents_monitor", "monitor_id", "confirmed_at"),
        # A retenção apaga checks; o banco precisa achar quem aponta para eles (SET NULL).
        Index("ix_incidents_last_check", "last_check_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(10), default="open")
    started_at: Mapped[datetime] = mapped_column(Timestamp)
    confirmed_at: Mapped[datetime] = mapped_column(Timestamp)
    ended_at: Mapped[datetime | None] = mapped_column(Timestamp)
    # Retrato da configuração no momento da abertura (RF03.12).
    failure_threshold: Mapped[int] = mapped_column(Integer)
    recovery_threshold: Mapped[int] = mapped_column(Integer)
    timeout_seconds: Mapped[int] = mapped_column(Integer)
    latency_threshold_ms: Mapped[int] = mapped_column(Integer)
    opening_reason: Mapped[str] = mapped_column(Text)
    resolution_reason: Mapped[str | None] = mapped_column(String(30))
    resolution_explanation: Mapped[str | None] = mapped_column(Text)
    failure_count: Mapped[int] = mapped_column(Integer)
    last_outcome: Mapped[str] = mapped_column(String(20))
    last_explanation: Mapped[str] = mapped_column(String(300))
    last_check_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("checks.id", ondelete="SET NULL")
    )


class IncidentEvent(Base):
    __tablename__ = "incident_events"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('first_failure', 'opened', 'error_changed', 'config_changed', "
            "'resolved', 'closed')",
            name="kind",
        ),
        Index("ix_incident_events_timeline", "incident_id", "occurred_at", "id"),
        Index("ix_incident_events_check", "check_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(20))
    occurred_at: Mapped[datetime] = mapped_column(Timestamp)
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    check_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("checks.id", ondelete="SET NULL")
    )


class HealthChange(Base):
    __tablename__ = "health_changes"
    __table_args__ = (
        Index("ix_health_changes_monitor", "monitor_id", "changed_at", "id"),
        Index("ix_health_changes_check", "check_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id", ondelete="RESTRICT"))
    changed_at: Mapped[datetime] = mapped_column(Timestamp)
    from_health: Mapped[str] = mapped_column(String(10))
    to_health: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(Text)
    check_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("checks.id", ondelete="SET NULL")
    )


class CoverageGap(Base):
    """Período em que checks previstos não foram executados (worker parado ou atrasado)."""

    __tablename__ = "coverage_gaps"
    __table_args__ = (
        CheckConstraint("gap_start < gap_end", name="ordered"),
        Index("ix_coverage_gaps_monitor", "monitor_id", "gap_start"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id", ondelete="RESTRICT"))
    gap_start: Mapped[datetime] = mapped_column(Timestamp)
    gap_end: Mapped[datetime] = mapped_column(Timestamp)
    reason: Mapped[str] = mapped_column(String(30))


class AlertDestination(Base):
    __tablename__ = "alert_destinations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    url: Mapped[str] = mapped_column(String(2048))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    updated_at: Mapped[datetime] = mapped_column(Timestamp)


class AlertEvent(Base):
    """Outbox: criado na mesma transação da mudança de incidente (RF06.1)."""

    __tablename__ = "alert_events"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('incident.opened', 'incident.resolved', 'incident.closed')", name="kind"
        ),
        Index("ix_alert_events_created", "created_at", "id"),
        # Notificações de um incidente, na página do incidente.
        Index("ix_alert_events_incident", "incident_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Chave estável "incident:{id}:{tipo}". Também é o event_id enviado ao destino.
    event_key: Mapped[str] = mapped_column(String(80), unique=True)
    kind: Mapped[str] = mapped_column(String(30))
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="RESTRICT"))
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id", ondelete="RESTRICT"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint("event_id", "destination_id", name="uq_deliveries_event_destination"),
        CheckConstraint("status IN ('pending', 'sending', 'delivered', 'failed')", name="status"),
        CheckConstraint("attempt_count >= 0", name="attempts"),
        # Consulta do entregador: entregas pendentes (ou com reserva vencida) por horário.
        Index(
            "ix_deliveries_due",
            "next_attempt_at",
            postgresql_where=text("status IN ('pending', 'sending')"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("alert_events.id", ondelete="RESTRICT"))
    destination_id: Mapped[int] = mapped_column(
        ForeignKey("alert_destinations.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(10), default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    # Para 'pending': quando tentar. Para 'sending': até quando vale a reserva.
    next_attempt_at: Mapped[datetime] = mapped_column(Timestamp)
    last_error: Mapped[str | None] = mapped_column(String(300))
    delivered_at: Mapped[datetime | None] = mapped_column(Timestamp)
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    updated_at: Mapped[datetime] = mapped_column(Timestamp)


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"
    __table_args__ = (
        UniqueConstraint("delivery_id", "attempt_number", name="uq_delivery_attempts_number"),
        CheckConstraint(
            "result IN ('success', 'retryable_error', 'permanent_error')", name="result"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("deliveries.id", ondelete="RESTRICT"))
    attempt_number: Mapped[int] = mapped_column(Integer)
    attempted_at: Mapped[datetime] = mapped_column(Timestamp)
    duration_ms: Mapped[int] = mapped_column(Integer)
    status_code: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(String(300))


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(255))
    pid: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(Timestamp)
    last_seen_at: Mapped[datetime] = mapped_column(Timestamp)
