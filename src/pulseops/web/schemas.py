"""Contratos JSON da API (entrada e saída)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pulseops.domain.monitor_rules import MAX_DESCRIPTION, MAX_NAME, MAX_URL, MonitorConfig


class MonitorIn(BaseModel):
    """Limites de tipo e tamanho aqui; regras combinadas em domain/monitor_rules.py."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=MAX_NAME)
    url: str = Field(max_length=MAX_URL)
    description: str = Field(default="", max_length=MAX_DESCRIPTION)
    method: Literal["GET", "HEAD"] = "GET"
    interval_seconds: int = 60
    timeout_seconds: int = 5
    accepted_status_codes: str = Field(default="200-299", max_length=100)
    latency_threshold_ms: int = 1000
    failure_threshold: int = 3
    recovery_threshold: int = 2

    def to_config(self) -> MonitorConfig:
        return MonitorConfig(**self.model_dump())


class MonitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    url: str
    method: str
    interval_seconds: int
    timeout_seconds: int
    accepted_status_codes: str
    latency_threshold_ms: int
    failure_threshold: int
    recovery_threshold: int
    state: str
    health: str
    health_reason: str
    stale: bool = False
    consecutive_failures: int
    consecutive_successes: int
    config_version: int
    next_run_at: datetime | None
    last_check_at: datetime | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class CheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_key: str
    trigger: str
    scheduled_at: datetime
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    status_code: int | None
    outcome: str | None
    explanation: str | None
    config_version: int


class CheckPage(BaseModel):
    items: list[CheckOut]
    next_cursor: str | None


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    monitor_id: int
    status: str
    started_at: datetime
    confirmed_at: datetime
    ended_at: datetime | None
    failure_threshold: int
    recovery_threshold: int
    timeout_seconds: int
    latency_threshold_ms: int
    opening_reason: str
    resolution_reason: str | None
    resolution_explanation: str | None
    failure_count: int
    last_outcome: str
    last_explanation: str


class IncidentPage(BaseModel):
    items: list[IncidentOut]
    next_cursor: str | None


class IncidentEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    occurred_at: datetime
    message: str
    details: dict[str, object]
    check_id: int | None


class AttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attempt_number: int
    attempted_at: datetime
    duration_ms: int
    status_code: int | None
    result: str
    error: str | None


class DeliveryOut(BaseModel):
    id: int
    destination: str
    status: str
    attempt_count: int
    next_attempt_at: datetime
    delivered_at: datetime | None
    last_error: str | None
    attempts: list[AttemptOut]


class AlertOut(BaseModel):
    event_id: str
    kind: str
    incident_id: int
    created_at: datetime
    deliveries: list[DeliveryOut]


class IncidentDetailOut(BaseModel):
    incident: IncidentOut
    events: list[IncidentEventOut]
    alerts: list[AlertOut]


class MetricsOut(BaseModel):
    start: datetime
    end: datetime
    evaluated_checks: int
    internal_errors: int
    by_outcome: dict[str, int]
    available_checks_pct: float | None
    healthy_checks_pct: float | None
    latency_samples: int
    latency_avg_ms: float | None
    latency_p95_ms: float | None
    incident_count: int
    incident_duration_seconds: float
    last_check_at: datetime | None
    gaps: list[tuple[datetime, datetime]]


class DestinationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    url: str = Field(max_length=MAX_URL)
    enabled: bool = True


class DestinationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class DestinationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    enabled: bool
    created_at: datetime


class SummaryOut(BaseModel):
    total: int
    by_health: dict[str, int]
    stale: int
    open_incidents: int
    pending_deliveries: int
    failed_deliveries: int
    worker_alive: bool
    worker_last_seen_at: datetime | None
    generated_at: datetime
