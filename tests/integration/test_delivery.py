"""Outbox e entregador (RF06): cenários 16 e 17."""

import asyncio
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from pulseops.config import Settings
from pulseops.db.models import AlertDestination, AlertEvent, Check, Delivery, DeliveryAttempt, Incident
from pulseops.db.session import SessionFactory
from pulseops.notifications.webhook import WebhookNotifier
from pulseops.security.url_policy import DestinationPolicy
from pulseops.services import alerts, incidents, processing
from pulseops.services.alerts import SendResult
from tests.support import FakeClock, ScriptedTarget
from tests.support_db import RecordingNotifier, create_monitor, incidents_of, make_worker, tick

HOOK = "https://hooks.example.com/pulseops"


async def add_destination(sessions: SessionFactory, clock: FakeClock, url: str = HOOK) -> None:
    async with sessions.begin() as session:
        session.add(
            AlertDestination(name="equipe", url=url, enabled=True, created_at=clock.now(), updated_at=clock.now())
        )


async def open_incident(sessions: SessionFactory, clock: FakeClock, settings: Settings, notifier: Any) -> Any:
    await create_monitor(sessions, clock, failure_threshold=1)
    target = ScriptedTarget(clock)
    target.mode = "error"
    worker = make_worker(sessions, clock, target, settings, notifier)
    await tick(worker, clock, 1)
    return worker, target


async def deliveries(sessions: SessionFactory) -> list[Delivery]:
    async with sessions() as session:
        return list(await session.scalars(select(Delivery).order_by(Delivery.id)))


async def attempts(sessions: SessionFactory) -> list[DeliveryAttempt]:
    async with sessions() as session:
        return list(await session.scalars(select(DeliveryAttempt).order_by(DeliveryAttempt.id)))


async def test_transition_creates_event_and_delivery_which_is_sent(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    await add_destination(sessions, clock)
    notifier = RecordingNotifier()
    worker, _ = await open_incident(sessions, clock, settings, notifier)
    [delivery] = await deliveries(sessions)
    assert delivery.status == "pending"

    assert await worker.run_deliveries_once() == 1
    [incident] = await incidents_of(sessions, 1)
    assert notifier.sent == [(HOOK, f"incident:{incident.id}:opened")]
    [delivered] = await deliveries(sessions)
    assert delivered.status == "delivered" and delivered.attempt_count == 1
    [attempt] = await attempts(sessions)
    assert (attempt.result, attempt.status_code) == ("success", 200)


async def test_without_destination_event_is_still_recorded(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    await open_incident(sessions, clock, settings, RecordingNotifier())
    async with sessions() as session:
        assert len(list(await session.scalars(select(AlertEvent)))) == 1
    assert await deliveries(sessions) == []


async def test_retries_with_capped_exponential_backoff(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    """Cenário 17 (parte do PulseOps): falhas temporárias são repetidas com espera crescente."""
    await add_destination(sessions, clock)
    notifier = RecordingNotifier()
    notifier.result = SendResult(False, False, 503, 3, "HTTP 503")
    worker, _ = await open_incident(sessions, clock, settings, notifier)

    await worker.run_deliveries_once()
    [d] = await deliveries(sessions)
    assert (d.status, d.attempt_count) == ("pending", 1)
    assert d.next_attempt_at - clock.now() == timedelta(seconds=5)

    clock.advance(4)
    assert await worker.run_deliveries_once() == 0  # ainda não venceu
    clock.advance(1)
    assert await worker.run_deliveries_once() == 1
    [d] = await deliveries(sessions)
    assert d.next_attempt_at - clock.now() == timedelta(seconds=10)

    notifier.result = SendResult(True, False, 200, 3, None)
    clock.advance(10)
    await worker.run_deliveries_once()
    [d] = await deliveries(sessions)
    assert (d.status, d.attempt_count) == ("delivered", 3)
    assert [a.result for a in await attempts(sessions)] == ["retryable_error", "retryable_error", "success"]


def test_backoff_is_capped() -> None:
    assert [alerts.backoff_delay(n, 5, 300) for n in range(1, 9)] == [5, 10, 20, 40, 80, 160, 300, 300]


@pytest.mark.parametrize(("status", "permanent"), [(400, True), (404, True), (408, False), (429, False), (500, False)])
def test_permanent_status_classification(status: int, permanent: bool) -> None:
    assert alerts.is_permanent_status(status) is permanent


async def test_attempts_are_limited_then_failed(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    await add_destination(sessions, clock)
    notifier = RecordingNotifier()
    notifier.result = SendResult(False, False, None, 5000, "sem resposta em 5 s")
    worker, _ = await open_incident(sessions, clock, settings, notifier)
    for _ in range(settings.webhook_max_attempts + 2):
        await worker.run_deliveries_once()
        clock.advance(settings.webhook_backoff_max_seconds)
    [d] = await deliveries(sessions)
    assert (d.status, d.attempt_count) == ("failed", settings.webhook_max_attempts)
    assert len(notifier.sent) == settings.webhook_max_attempts


async def test_client_error_is_permanent_failure(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    await add_destination(sessions, clock)
    notifier = RecordingNotifier()
    notifier.result = SendResult(False, True, 404, 3, "HTTP 404")
    worker, _ = await open_incident(sessions, clock, settings, notifier)
    await worker.run_deliveries_once()
    [d] = await deliveries(sessions)
    assert (d.status, d.attempt_count) == ("failed", 1)
    assert [a.result for a in await attempts(sessions)] == ["permanent_error"]


async def test_expired_lease_is_retried_which_may_duplicate(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    """Entrega "pelo menos uma vez": se o worker morre depois de enviar e antes de gravar,
    a reserva expira e o mesmo evento é enviado de novo (RF06.8)."""
    await add_destination(sessions, clock)
    await open_incident(sessions, clock, settings, RecordingNotifier())
    [first] = await alerts.claim_due_deliveries(sessions, now=clock.now(), limit=10, lease_seconds=35)
    # ... o processo morreu aqui, sem gravar o resultado.
    assert await alerts.claim_due_deliveries(sessions, now=clock.now(), limit=10, lease_seconds=35) == []
    clock.advance(36)
    [second] = await alerts.claim_due_deliveries(sessions, now=clock.now(), limit=10, lease_seconds=35)
    assert second.event_key == first.event_key  # mesma identidade: o receptor deduplica
    assert second.attempt_number == 2


async def test_outbox_event_is_atomic_with_incident(
    sessions: SessionFactory, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Se a criação do evento falha, o incidente e o resultado do check também não são gravados."""
    await add_destination(sessions, clock)
    monitor = await create_monitor(sessions, clock, failure_threshold=1)
    target = ScriptedTarget(clock)
    target.mode = "error"
    [run] = await processing.claim_due_runs(sessions, now=clock.now(), limit=5)
    observation = await target.checker().check(run.target)

    original = incidents.enqueue_incident_alert

    async def broken(*args: Any, **kwargs: Any) -> Any:
        await original(*args, **kwargs)
        raise RuntimeError("falha simulada depois de criar o evento")

    monkeypatch.setattr(incidents, "enqueue_incident_alert", broken)
    with pytest.raises(RuntimeError):
        await processing.record_result(sessions, run, observation)

    async with sessions() as session:
        assert list(await session.scalars(select(Incident))) == []
        assert list(await session.scalars(select(AlertEvent))) == []
        check = await session.get(Check, run.check_id)
        assert check is not None and check.status == "running"  # rollback completo
    assert monitor.id == run.monitor_id


async def test_slow_webhook_does_not_block_checks(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    """Cenário 16: enquanto um envio está travado, as verificações continuam."""
    await add_destination(sessions, clock)
    release = asyncio.Event()

    class StuckNotifier:
        async def send(self, url: str, event_id: str, payload: dict[str, Any]) -> SendResult:
            await release.wait()
            return SendResult(True, False, 200, 1, None)

    worker, target = await open_incident(sessions, clock, settings, StuckNotifier())
    sending = asyncio.create_task(worker.run_deliveries_once())
    await asyncio.sleep(0)  # o envio começou e está preso

    target.mode = "ok"
    for _ in range(3):
        await tick(worker, clock, 60)
    assert not sending.done()
    [incident] = await incidents_of(sessions, 1)
    assert incident.status == "resolved"  # verificações seguiram e recuperaram o incidente

    release.set()
    assert await sending == 1


async def test_webhook_notifier_sends_event_id_and_classifies_errors(clock: FakeClock) -> None:
    seen: list[httpx.Request] = []
    responses = iter([httpx.Response(204), httpx.Response(503), httpx.Response(404)])

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return next(responses)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    notifier = WebhookNotifier(client, clock, DestinationPolicy(), timeout_seconds=1)
    ok = await notifier.send(HOOK, "incident:1:opened", {"event_id": "incident:1:opened"})
    retry = await notifier.send(HOOK, "incident:1:opened", {})
    permanent = await notifier.send(HOOK, "incident:1:opened", {})
    assert (ok.ok, retry.ok, retry.permanent, permanent.permanent) == (True, False, False, True)
    assert seen[0].headers["X-PulseOps-Event-Id"] == "incident:1:opened"
    assert seen[0].headers["content-type"] == "application/json"


async def test_webhook_timeout_is_retryable(clock: FakeClock) -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(slow))
    notifier = WebhookNotifier(client, clock, DestinationPolicy(), timeout_seconds=0.05)
    result = await notifier.send(HOOK, "incident:1:opened", {})
    assert (result.ok, result.permanent, result.error) == (False, False, "sem resposta em 0.05 s")


async def test_blocked_destination_fails_permanently(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    """T8: um destino que aponta para a rede interna nunca é chamado."""
    await add_destination(sessions, clock, url="http://10.0.0.5/hook")
    called: list[httpx.Request] = []
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: called.append(r) or httpx.Response(200)))
    notifier = WebhookNotifier(client, clock, DestinationPolicy(), timeout_seconds=1)
    worker, _ = await open_incident(sessions, clock, settings, notifier)
    await worker.run_deliveries_once()
    [d] = await deliveries(sessions)
    assert d.status == "failed" and d.last_error is not None and "bloqueado" in d.last_error
    assert called == []
