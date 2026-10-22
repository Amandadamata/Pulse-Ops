"""Regra de transição de saúde e incidentes (RF03), sem banco."""

from datetime import timedelta

import pytest

from pulseops.domain.health import (
    Health,
    HealthTracker,
    IncidentAction,
    Observation,
    Thresholds,
    TrackerState,
)
from pulseops.domain.outcomes import Outcome
from tests.support import START

INITIAL = TrackerState(Health.NO_DATA, 0, 0, None, incident_open=False)


def run(
    outcomes: list[Outcome], failure: int = 3, recovery: int = 2, state: TrackerState = INITIAL
):
    tracker = HealthTracker(Thresholds(failure, recovery))
    decisions = []
    for i, outcome in enumerate(outcomes):
        obs = Observation(outcome, START + timedelta(minutes=i), f"resultado {i}")
        decision = tracker.apply(state, obs)
        decisions.append(decision)
        state = decision.state
    return state, decisions


F, S = Outcome.TIMEOUT, Outcome.HEALTHY


def actions(decisions):
    return [d.incident_action for d in decisions]


def test_mandatory_example_fail_fail_success_opens_nothing() -> None:
    state, decisions = run([F, F, S])
    assert IncidentAction.OPEN not in actions(decisions)
    assert (state.consecutive_failures, state.consecutive_successes) == (0, 1)
    assert state.incident_open is False


def test_mandatory_example_three_failures_open_exactly_one_incident() -> None:
    state, decisions = run([F, F, F])
    assert actions(decisions) == [IncidentAction.NONE, IncidentAction.NONE, IncidentAction.OPEN]
    assert state.incident_open and state.health is Health.DOWN


def test_mandatory_example_more_failures_update_the_same_incident() -> None:
    _, decisions = run([F, F, F, F, F])
    assert actions(decisions).count(IncidentAction.OPEN) == 1
    assert actions(decisions)[3:] == [IncidentAction.UPDATE, IncidentAction.UPDATE]


def test_mandatory_example_recovery_requires_configured_successes() -> None:
    state, decisions = run([F, F, F, S, S], recovery=2)
    assert actions(decisions)[3:] == [IncidentAction.NONE, IncidentAction.RESOLVE]
    assert decisions[3].state.health is Health.DOWN  # um sucesso não basta
    assert state.incident_open is False and state.health is Health.HEALTHY


def test_alternating_results_never_reach_threshold() -> None:
    state, decisions = run([F, S, F, S, F, F, S, F, F])
    assert IncidentAction.OPEN not in actions(decisions)
    assert state.consecutive_failures == 2


def test_failure_during_recovery_resets_success_counter() -> None:
    _, decisions = run([F, F, F, S, F, S, S], recovery=2)
    assert actions(decisions)[-1] is IncidentAction.RESOLVE
    assert actions(decisions)[4] is IncidentAction.UPDATE


def test_first_failure_time_is_kept_until_confirmation() -> None:
    state, decisions = run([F, F, F])
    assert state.first_failure_at == START  # primeira falha, não a da confirmação
    assert decisions[2].reason.startswith("Incidente confirmado após 3 falhas consecutivas")


def test_slow_is_degraded_but_not_a_failure() -> None:
    state, decisions = run([Outcome.SLOW, Outcome.SLOW, Outcome.SLOW, Outcome.SLOW], failure=1)
    assert IncidentAction.OPEN not in actions(decisions)
    assert state.health is Health.DEGRADED
    assert state.consecutive_successes == 4


def test_slow_response_counts_towards_recovery() -> None:
    state, decisions = run([F, Outcome.SLOW, Outcome.SLOW], failure=1, recovery=2)
    assert actions(decisions)[-1] is IncidentAction.RESOLVE
    assert state.health is Health.DEGRADED  # recuperou, mas continua lento


def test_internal_error_changes_nothing() -> None:
    before, _ = run([F, F])
    after, decisions = run([Outcome.INTERNAL_ERROR] * 5, state=before)
    assert after == before
    assert all(a is IncidentAction.NONE for a in actions(decisions))


@pytest.mark.parametrize(
    "outcome",
    [
        Outcome.UNEXPECTED_STATUS,
        Outcome.TIMEOUT,
        Outcome.CONNECTION_ERROR,
        Outcome.TLS_ERROR,
        Outcome.BLOCKED,
    ],
)
def test_every_target_failure_category_counts(outcome: Outcome) -> None:
    state, _ = run([outcome], failure=1)
    assert state.incident_open


def test_failure_below_threshold_is_degraded_with_progress_message() -> None:
    state, decisions = run([F])
    assert state.health is Health.DEGRADED
    assert decisions[0].reason == "Falha 1 de 3 necessárias para abrir incidente: resultado 0."


def test_health_changed_flag() -> None:
    _, decisions = run([S, S, F])
    assert [d.health_changed for d in decisions] == [True, False, True]
