"""esquema inicial

Revision ID: 0001
Revises:
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_destinations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_destinations")),
        sa.UniqueConstraint("name", name=op.f("uq_alert_destinations_name")),
    )
    op.create_table(
        "monitors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("method", sa.String(length=4), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("accepted_status_codes", sa.String(length=100), nullable=False),
        sa.Column("latency_threshold_ms", sa.Integer(), nullable=False),
        sa.Column("failure_threshold", sa.Integer(), nullable=False),
        sa.Column("recovery_threshold", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=10), nullable=False),
        sa.Column("health", sa.String(length=10), nullable=False),
        sa.Column("health_reason", sa.Text(), nullable=False),
        sa.Column("health_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("consecutive_successes", sa.Integer(), nullable=False),
        sa.Column("first_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_requested", sa.Boolean(), nullable=False),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(state = 'archived') = (archived_at IS NOT NULL)", name=op.f("ck_monitors_archived_at")
        ),
        sa.CheckConstraint(
            "health IN ('no_data', 'healthy', 'degraded', 'down', 'paused')",
            name=op.f("ck_monitors_health"),
        ),
        sa.CheckConstraint("method IN ('GET', 'HEAD')", name=op.f("ck_monitors_method")),
        sa.CheckConstraint(
            "state IN ('active', 'paused', 'archived')", name=op.f("ck_monitors_state")
        ),
        sa.CheckConstraint(
            "consecutive_failures >= 0 AND consecutive_successes >= 0",
            name=op.f("ck_monitors_counters"),
        ),
        sa.CheckConstraint(
            "failure_threshold BETWEEN 1 AND 10", name=op.f("ck_monitors_failure_threshold")
        ),
        sa.CheckConstraint(
            "interval_seconds BETWEEN 2 AND 86400", name=op.f("ck_monitors_interval")
        ),
        sa.CheckConstraint(
            "latency_threshold_ms BETWEEN 50 AND timeout_seconds * 1000",
            name=op.f("ck_monitors_latency"),
        ),
        sa.CheckConstraint(
            "recovery_threshold BETWEEN 1 AND 10", name=op.f("ck_monitors_recovery_threshold")
        ),
        sa.CheckConstraint(
            "timeout_seconds < interval_seconds", name=op.f("ck_monitors_timeout_lt_interval")
        ),
        sa.CheckConstraint("timeout_seconds BETWEEN 1 AND 30", name=op.f("ck_monitors_timeout")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_monitors")),
    )
    op.create_index(
        "ix_monitors_due",
        "monitors",
        ["next_run_at"],
        unique=False,
        postgresql_where=sa.text("state = 'active'"),
    )
    op.create_index(
        "uq_monitors_active_name",
        "monitors",
        [sa.literal_column("lower(name)")],
        unique=True,
        postgresql_where=sa.text("state <> 'archived'"),
    )
    op.create_table(
        "operators",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operators")),
        sa.UniqueConstraint("username", name=op.f("uq_operators_username")),
    )
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(length=100), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("worker_id", name=op.f("pk_worker_heartbeats")),
    )
    op.create_table(
        "checks",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("monitor_id", sa.Integer(), nullable=False),
        sa.Column("run_key", sa.String(length=80), nullable=False),
        sa.Column("trigger", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=True),
        sa.Column("explanation", sa.String(length=300), nullable=True),
        sa.CheckConstraint(
            "(status = 'running' AND outcome IS NULL AND finished_at IS NULL) OR (status = 'completed' AND outcome IS NOT NULL AND finished_at IS NOT NULL)",
            name=op.f("ck_checks_completed_has_outcome"),
        ),
        sa.CheckConstraint(
            "outcome IN ('healthy', 'slow', 'unexpected_status', 'timeout', 'connection_error', 'tls_error', 'blocked', 'internal_error')",
            name=op.f("ck_checks_outcome"),
        ),
        sa.CheckConstraint("status IN ('running', 'completed')", name=op.f("ck_checks_status")),
        sa.CheckConstraint("trigger IN ('scheduled', 'manual')", name=op.f("ck_checks_trigger")),
        sa.ForeignKeyConstraint(
            ["monitor_id"],
            ["monitors.id"],
            name=op.f("fk_checks_monitor_id_monitors"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_checks")),
        sa.UniqueConstraint("run_key", name=op.f("uq_checks_run_key")),
    )
    op.create_index(
        "ix_checks_monitor_history", "checks", ["monitor_id", "started_at", "id"], unique=False
    )
    op.create_index("ix_checks_started_at", "checks", ["started_at"], unique=False)
    op.create_index(
        "uq_checks_one_running_per_monitor",
        "checks",
        ["monitor_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_table(
        "coverage_gaps",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("monitor_id", sa.Integer(), nullable=False),
        sa.Column("gap_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gap_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=30), nullable=False),
        sa.CheckConstraint("gap_start < gap_end", name=op.f("ck_coverage_gaps_ordered")),
        sa.ForeignKeyConstraint(
            ["monitor_id"],
            ["monitors.id"],
            name=op.f("fk_coverage_gaps_monitor_id_monitors"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coverage_gaps")),
    )
    op.create_index(
        "ix_coverage_gaps_monitor", "coverage_gaps", ["monitor_id", "gap_start"], unique=False
    )
    op.create_table(
        "operator_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("operator_id", sa.Integer(), nullable=False),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["operators.id"],
            name=op.f("fk_operator_sessions_operator_id_operators"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_hash", name=op.f("pk_operator_sessions")),
    )
    op.create_index(
        op.f("ix_operator_sessions_expires_at"), "operator_sessions", ["expires_at"], unique=False
    )
    op.create_table(
        "health_changes",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("monitor_id", sa.Integer(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("from_health", sa.String(length=10), nullable=False),
        sa.Column("to_health", sa.String(length=10), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("check_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["check_id"],
            ["checks.id"],
            name=op.f("fk_health_changes_check_id_checks"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["monitor_id"],
            ["monitors.id"],
            name=op.f("fk_health_changes_monitor_id_monitors"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_health_changes")),
    )
    op.create_index("ix_health_changes_check", "health_changes", ["check_id"], unique=False)
    op.create_index(
        "ix_health_changes_monitor",
        "health_changes",
        ["monitor_id", "changed_at", "id"],
        unique=False,
    )
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("monitor_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_threshold", sa.Integer(), nullable=False),
        sa.Column("recovery_threshold", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("latency_threshold_ms", sa.Integer(), nullable=False),
        sa.Column("opening_reason", sa.Text(), nullable=False),
        sa.Column("resolution_reason", sa.String(length=30), nullable=True),
        sa.Column("resolution_explanation", sa.Text(), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("last_outcome", sa.String(length=20), nullable=False),
        sa.Column("last_explanation", sa.String(length=300), nullable=False),
        sa.Column("last_check_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "(status = 'open') = (ended_at IS NULL)", name=op.f("ck_incidents_ended_when_not_open")
        ),
        sa.CheckConstraint(
            "status IN ('open', 'resolved', 'closed')", name=op.f("ck_incidents_status")
        ),
        sa.CheckConstraint(
            "started_at <= confirmed_at", name=op.f("ck_incidents_started_before_confirmed")
        ),
        sa.ForeignKeyConstraint(
            ["last_check_id"],
            ["checks.id"],
            name=op.f("fk_incidents_last_check_id_checks"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["monitor_id"],
            ["monitors.id"],
            name=op.f("fk_incidents_monitor_id_monitors"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
    )
    op.create_index("ix_incidents_confirmed", "incidents", ["confirmed_at", "id"], unique=False)
    op.create_index("ix_incidents_last_check", "incidents", ["last_check_id"], unique=False)
    op.create_index(
        "ix_incidents_monitor", "incidents", ["monitor_id", "confirmed_at"], unique=False
    )
    op.create_index(
        "uq_incidents_one_open_per_monitor",
        "incidents",
        ["monitor_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_table(
        "alert_events",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("event_key", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("monitor_id", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('incident.opened', 'incident.resolved', 'incident.closed')",
            name=op.f("ck_alert_events_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_alert_events_incident_id_incidents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["monitor_id"],
            ["monitors.id"],
            name=op.f("fk_alert_events_monitor_id_monitors"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_events")),
        sa.UniqueConstraint("event_key", name=op.f("uq_alert_events_event_key")),
    )
    op.create_index("ix_alert_events_created", "alert_events", ["created_at", "id"], unique=False)
    op.create_index("ix_alert_events_incident", "alert_events", ["incident_id"], unique=False)
    op.create_table(
        "incident_events",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("check_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('first_failure', 'opened', 'error_changed', 'config_changed', 'resolved', 'closed')",
            name=op.f("ck_incident_events_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["check_id"],
            ["checks.id"],
            name=op.f("fk_incident_events_check_id_checks"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_incident_events_incident_id_incidents"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incident_events")),
    )
    op.create_index("ix_incident_events_check", "incident_events", ["check_id"], unique=False)
    op.create_index(
        "ix_incident_events_timeline",
        "incident_events",
        ["incident_id", "occurred_at", "id"],
        unique=False,
    )
    op.create_table(
        "deliveries",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("destination_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'delivered', 'failed')",
            name=op.f("ck_deliveries_status"),
        ),
        sa.CheckConstraint("attempt_count >= 0", name=op.f("ck_deliveries_attempts")),
        sa.ForeignKeyConstraint(
            ["destination_id"],
            ["alert_destinations.id"],
            name=op.f("fk_deliveries_destination_id_alert_destinations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["alert_events.id"],
            name=op.f("fk_deliveries_event_id_alert_events"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deliveries")),
        sa.UniqueConstraint("event_id", "destination_id", name="uq_deliveries_event_destination"),
    )
    op.create_index(
        "ix_deliveries_due",
        "deliveries",
        ["next_attempt_at"],
        unique=False,
        postgresql_where=sa.text("status IN ('pending', 'sending')"),
    )
    op.create_table(
        "delivery_attempts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("delivery_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.CheckConstraint(
            "result IN ('success', 'retryable_error', 'permanent_error')",
            name=op.f("ck_delivery_attempts_result"),
        ),
        sa.ForeignKeyConstraint(
            ["delivery_id"],
            ["deliveries.id"],
            name=op.f("fk_delivery_attempts_delivery_id_deliveries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_delivery_attempts")),
        sa.UniqueConstraint("delivery_id", "attempt_number", name="uq_delivery_attempts_number"),
    )


def downgrade() -> None:
    op.drop_table("delivery_attempts")
    op.drop_index(
        "ix_deliveries_due",
        table_name="deliveries",
        postgresql_where=sa.text("status IN ('pending', 'sending')"),
    )
    op.drop_table("deliveries")
    op.drop_index("ix_incident_events_timeline", table_name="incident_events")
    op.drop_index("ix_incident_events_check", table_name="incident_events")
    op.drop_table("incident_events")
    op.drop_index("ix_alert_events_incident", table_name="alert_events")
    op.drop_index("ix_alert_events_created", table_name="alert_events")
    op.drop_table("alert_events")
    op.drop_index(
        "uq_incidents_one_open_per_monitor",
        table_name="incidents",
        postgresql_where=sa.text("status = 'open'"),
    )
    op.drop_index("ix_incidents_monitor", table_name="incidents")
    op.drop_index("ix_incidents_last_check", table_name="incidents")
    op.drop_index("ix_incidents_confirmed", table_name="incidents")
    op.drop_table("incidents")
    op.drop_index("ix_health_changes_monitor", table_name="health_changes")
    op.drop_index("ix_health_changes_check", table_name="health_changes")
    op.drop_table("health_changes")
    op.drop_index(op.f("ix_operator_sessions_expires_at"), table_name="operator_sessions")
    op.drop_table("operator_sessions")
    op.drop_index("ix_coverage_gaps_monitor", table_name="coverage_gaps")
    op.drop_table("coverage_gaps")
    op.drop_index(
        "uq_checks_one_running_per_monitor",
        table_name="checks",
        postgresql_where=sa.text("status = 'running'"),
    )
    op.drop_index("ix_checks_started_at", table_name="checks")
    op.drop_index("ix_checks_monitor_history", table_name="checks")
    op.drop_table("checks")
    op.drop_table("worker_heartbeats")
    op.drop_table("operators")
    op.drop_index(
        "uq_monitors_active_name",
        table_name="monitors",
        postgresql_where=sa.text("state <> 'archived'"),
    )
    op.drop_index(
        "ix_monitors_due", table_name="monitors", postgresql_where=sa.text("state = 'active'")
    )
    op.drop_table("monitors")
    op.drop_table("alert_destinations")
