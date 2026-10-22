"""Etapa 3: cadastrar monitor → worker verifica → resultado persistido → consulta pela API."""

import httpx

from pulseops.config import Settings
from pulseops.db.session import SessionFactory
from pulseops.services.alerts import SendResult
from pulseops.worker.runner import Worker
from tests.support import FakeClock, ScriptedTarget


class NullNotifier:
    async def send(self, url: str, event_id: str, payload: dict[str, object]) -> SendResult:
        return SendResult(True, False, 200, 1, None)


async def test_monitor_created_by_api_is_checked_by_worker_and_listed(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    created = await api.post(
        "/api/v1/monitors",
        json={"name": "API de pedidos", "url": "https://pedidos.example.com/health"},
    )
    assert created.status_code == 201, created.text
    monitor = created.json()
    assert monitor["health"] == "no_data"

    target = ScriptedTarget(clock)
    worker = Worker(
        sessions=sessions,
        checker=target.checker(),
        notifier=NullNotifier(),
        clock=clock,
        settings=settings,
    )
    assert await worker.run_checks_once() == 1
    assert target.requests[0].url == "https://pedidos.example.com/health"

    page = (await api.get(f"/api/v1/monitors/{monitor['id']}/checks")).json()
    assert len(page["items"]) == 1
    check = page["items"][0]
    assert check["outcome"] == "healthy"
    assert check["status_code"] == 200
    assert check["run_key"].startswith(f"{monitor['id']}:")
    assert check["duration_ms"] == 20  # medido pelo relógio monotônico controlado

    detail = (await api.get(f"/api/v1/monitors/{monitor['id']}")).json()
    assert detail["health"] == "healthy"
    assert detail["last_check_at"] is not None
