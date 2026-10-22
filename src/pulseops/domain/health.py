"""Regra de transição de saúde e de incidentes (RF03).

Este módulo não conhece banco nem HTTP: recebe o estado atual de um monitor e o
resultado de um check, e devolve o novo estado e o que fazer com o incidente.
Isso permite testar a regra inteira com objetos simples.
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
            Health.NO_DATA: "Sem dados",
            Health.HEALTHY: "Saudável",
            Health.DEGRADED: "Degradado",
            Health.DOWN: "Indisponível",
            Health.PAUSED: "Pausado",
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
    """Parte do monitor que a regra lê e altera. Fica persistida no banco."""

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
    """Aplica um resultado de check ao estado do monitor.

    Regras (docs/requisitos.md, RF03):
    - falha soma em `consecutive_failures` e zera os sucessos; sucesso faz o contrário;
    - erro interno não muda nada;
    - o incidente abre quando as falhas atingem `failure_threshold` e fecha quando os
      sucessos atingem `recovery_threshold`.
    """

    def __init__(self, thresholds: Thresholds) -> None:
        self._thresholds = thresholds

    def apply(self, state: TrackerState, obs: Observation) -> Decision:
        if obs.outcome is Outcome.INTERNAL_ERROR:
            return Decision(
                state,
                IncidentAction.NONE,
                state.health,
                f"Erro interno do PulseOps ignorado na contagem: {obs.explanation}",
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
            reason = f"Incidente continua aberto; último resultado: {obs.explanation}."
            new = replace(new, health=Health.DOWN)
            return Decision(new, IncidentAction.UPDATE, state.health, reason)

        if failures >= limit:
            reason = (
                f"Incidente confirmado após {failures} "
                f"{_plural(failures, 'falha consecutiva', 'falhas consecutivas')}; "
                f"último resultado: {obs.explanation}."
            )
            new = replace(new, health=Health.DOWN, incident_open=True)
            return Decision(new, IncidentAction.OPEN, state.health, reason)

        reason = f"Falha {failures} de {limit} necessárias para abrir incidente: {obs.explanation}."
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
                    f"Recuperado após {successes} "
                    f"{_plural(successes, 'sucesso consecutivo', 'sucessos consecutivos')}; "
                    f"último resultado: {obs.explanation}."
                )
                new = replace(new, health=health, incident_open=False)
                return Decision(new, IncidentAction.RESOLVE, state.health, reason)
            reason = (
                f"Sucesso {successes} de {limit} necessários para encerrar o incidente: "
                f"{obs.explanation}."
            )
            return Decision(
                replace(new, health=Health.DOWN), IncidentAction.NONE, state.health, reason
            )

        if obs.outcome is Outcome.SLOW:
            reason = f"Resposta lenta: {obs.explanation}."
            return Decision(
                replace(new, health=Health.DEGRADED), IncidentAction.NONE, state.health, reason
            )
        reason = f"Respondendo normalmente: {obs.explanation}."
        return Decision(
            replace(new, health=Health.HEALTHY), IncidentAction.NONE, state.health, reason
        )


def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural
