"""Health and incident transition rule (RF03).

This module knows nothing about the database or HTTP: it receives a monitor's current
state and a check result, and returns the new state and what to do with the incident.
That makes it possible to test the whole rule with plain objects.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from pulseops.domain.outcomes import Outcome


class Health(StrEnum):
    NO_DATA = "no_data"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    PAUSED = "paused"

    @property
    def label(self) -> str:
        return {
            Health.NO_DATA: "No data",
            Health.HEALTHY: "Healthy",
            Health.DEGRADED: "Degraded",
            Health.DOWN: "Down",
            Health.PAUSED: "Paused",
        }[self]


class IncidentAction(StrEnum):
    NONE = "none"
    OPEN = "open"
    UPDATE = "update"
    RESOLVE = "resolve"


@dataclass(frozen=True)
class Thresholds:
    failure_threshold: int
    recovery_threshold: int


@dataclass(frozen=True)
class TrackerState:
    """The part of the monitor that the rule reads and changes. It is persisted in the database."""

    health: Health
    consecutive_failures: int
    consecutive_successes: int
    first_failure_at: datetime | None
    incident_open: bool


@dataclass(frozen=True)
class Observation:
    outcome: Outcome
    observed_at: datetime
    explanation: str


@dataclass(frozen=True)
class Decision:
    state: TrackerState
    incident_action: IncidentAction
    previous_health: Health
    reason: str

    @property
    def health_changed(self) -> bool:
        return self.state.health != self.previous_health


class HealthTracker:
    """Applies a check result to the monitor state.

    Rules (docs/requisitos.md, RF03):
    - a failure adds to `consecutive_failures` and resets successes; a success does the opposite;
    - an internal error changes nothing;
    - the incident opens when failures reach `failure_threshold` and closes when
      successes reach `recovery_threshold`.
    """

    def __init__(self, thresholds: Thresholds) -> None:
        self._thresholds = thresholds

    def apply(self, state: TrackerState, obs: Observation) -> Decision:
        if obs.outcome is Outcome.INTERNAL_ERROR:
            return Decision(
                state,
                IncidentAction.NONE,
                state.health,
                f"PulseOps internal error left out of the count: {obs.explanation}",
            )
        if obs.outcome.is_failure:
            return self._on_failure(state, obs)
        return self._on_success(state, obs)

    def _on_failure(self, state: TrackerState, obs: Observation) -> Decision:
        failures = state.consecutive_failures + 1
        first_failure_at = state.first_failure_at if state.consecutive_failures else obs.observed_at
        new = replace(
            state,
            consecutive_failures=failures,
            consecutive_successes=0,
            first_failure_at=first_failure_at,
        )
        limit = self._thresholds.failure_threshold

        if state.incident_open:
            reason = f"Incident still open; last result: {obs.explanation}."
            new = replace(new, health=Health.DOWN)
            return Decision(new, IncidentAction.UPDATE, state.health, reason)

        if failures >= limit:
            reason = (
                f"Incident confirmed after {failures} "
                f"{_plural(failures, 'consecutive failure', 'consecutive failures')}; "
                f"last result: {obs.explanation}."
            )
            new = replace(new, health=Health.DOWN, incident_open=True)
            return Decision(new, IncidentAction.OPEN, state.health, reason)

        reason = f"Failure {failures} of {limit} needed to open an incident: {obs.explanation}."
        new = replace(new, health=Health.DEGRADED)
        return Decision(new, IncidentAction.NONE, state.health, reason)

    def _on_success(self, state: TrackerState, obs: Observation) -> Decision:
        successes = state.consecutive_successes + 1
        new = replace(
            state,
            consecutive_failures=0,
            consecutive_successes=successes,
            first_failure_at=None,
        )
        limit = self._thresholds.recovery_threshold

        if state.incident_open:
            if successes >= limit:
                health = Health.DEGRADED if obs.outcome is Outcome.SLOW else Health.HEALTHY
                reason = (
                    f"Recovered after {successes} "
                    f"{_plural(successes, 'consecutive success', 'consecutive successes')}; "
                    f"last result: {obs.explanation}."
                )
                new = replace(new, health=health, incident_open=False)
                return Decision(new, IncidentAction.RESOLVE, state.health, reason)
            reason = (
                f"Success {successes} of {limit} needed to close the incident: {obs.explanation}."
            )
            return Decision(
                replace(new, health=Health.DOWN), IncidentAction.NONE, state.health, reason
            )

        if obs.outcome is Outcome.SLOW:
            reason = f"Slow response: {obs.explanation}."
            return Decision(
                replace(new, health=Health.DEGRADED), IncidentAction.NONE, state.health, reason
            )
        reason = f"Respondendo normalmente: {obs.explanation}."
        return Decision(
            replace(new, health=Health.HEALTHY), IncidentAction.NONE, state.health, reason
        )


def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural
