"""Jinja2 configuration and formatting filters used in the templates."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, pass_context
from jinja2.runtime import Context

from pulseops.domain.health import Health
from pulseops.domain.outcomes import Outcome

# autoescape=True: every value inserted into the HTML is escaped (XSS protection, T12).
_env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=True)
templates = Jinja2Templates(env=_env)


@pass_context
def local_datetime(context: Context, value: datetime | None) -> str:
    """Converts from UTC to the configured display timezone (RF05.6)."""
    if value is None:
        return "—"
    tz: ZoneInfo = context["tz"]
    return value.astimezone(tz).strftime("%d/%m/%Y %H:%M:%S")


def percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1f}%".replace(".", ",")


def milliseconds(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.0f} ms"


def duration(value: timedelta | None) -> str:
    if value is None:
        return "—"
    total = int(value.total_seconds())
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min {seconds:02d} s"
    return f"{seconds} s"


def health_label(value: str) -> str:
    try:
        return Health(value).label
    except ValueError:
        return value


def outcome_label(value: str | None) -> str:
    if value is None:
        return "—"
    try:
        return Outcome(value).label
    except ValueError:
        return value


STATE_LABELS = {"active": "Active", "paused": "Paused", "archived": "Archived"}
INCIDENT_LABELS = {"open": "Open", "resolved": "Resolved", "closed": "Closed without recovery"}
DELIVERY_LABELS = {
    "pending": "Pending",
    "sending": "Sending",
    "delivered": "Delivered",
    "failed": "Failed",
}
EVENT_LABELS = {
    "first_failure": "First failure",
    "opened": "Incident confirmed",
    "error_changed": "Failure type changed",
    "config_changed": "Configuration changed",
    "resolved": "Recovered",
    "closed": "Closed by the operator",
}

filters: dict[str, Any] = {
    "dt": local_datetime,
    "pct": percent,
    "ms": milliseconds,
    "duration": duration,
    "health_label": health_label,
    "outcome_label": outcome_label,
    "state_label": STATE_LABELS.get,
    "incident_label": INCIDENT_LABELS.get,
    "delivery_label": DELIVERY_LABELS.get,
    "event_label": EVENT_LABELS.get,
}
templates.env.filters.update(filters)
