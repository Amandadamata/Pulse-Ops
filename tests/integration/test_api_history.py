"""Histórico paginado e filtros (RF04) e cenário 18 (UTC e limites [início, fim))."""

from datetime import timedelta

import httpx

from pulseops.config import Settings
from pulseops.db.session import SessionFactory
from tests.support import START, FakeClock, ScriptedTarget
from tests.support_db import create_monitor, insert_checks, make_worker, tick


async def seed(
    sessions: SessionFactory, clock: FakeClock, settings: Settings, modes: list[str]
) -> int:
    monitor = await create_monitor(sessions, clock, failure_threshold=10)
    target = ScriptedTarget(clock)
    worker = make_worker(sessions, clock, target, settings)
    for mode in modes:
        target.mode = mode
        await tick(worker, clock, 60)
    return monitor.id


async def test_cursor_pagination_is_stable_and_complete(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    monitor_id = await seed(sessions, clock, settings, ["ok"] * 7)
    seen, cursor = [], None
    while True:
        params = {"limit": 3} | ({"cursor": cursor} if cursor else {})
        page = (await api.get(f"/api/v1/monitors/{monitor_id}/checks", params=params)).json()
        seen += [c["id"] for c in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == sorted(seen, reverse=True) and len(seen) == len(set(seen)) == 7


async def test_filter_by_outcome(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    monitor_id = await seed(sessions, clock, settings, ["ok", "error", "ok", "timeout", "error"])
    page = (
        await api.get(
            f"/api/v1/monitors/{monitor_id}/checks", params={"outcome": "unexpected_status"}
        )
    ).json()
    assert [c["status_code"] for c in page["items"]] == [500, 500]
    assert (
        await api.get(f"/api/v1/monitors/{monitor_id}/checks", params={"outcome": "xyz"})
    ).status_code == 422


async def test_window_start_inclusive_end_exclusive(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock
) -> None:
    """Cenário 18: checks exatamente às 12:00, 12:01 e 12:02 UTC; [12:01, 12:02) pega só 12:01."""
    monitor = await create_monitor(sessions, clock)
    await insert_checks(sessions, monitor.id, [("healthy", 10)] * 3, start=START, step=60)
    start = (START + timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    end = (START + timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    page = (
        await api.get(f"/api/v1/monitors/{monitor.id}/checks", params={"from": start, "to": end})
    ).json()
    assert [c["started_at"] for c in page["items"]] == ["2026-01-15T12:01:00Z"]


async def test_window_with_other_timezone_is_converted(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    monitor_id = await seed(sessions, clock, settings, ["ok", "ok", "ok"])
    # 09:01 em São Paulo (UTC−3) é 12:01 UTC.
    params = {"from": "2026-01-15T09:01:00-03:00", "to": "2026-01-15T09:02:00-03:00"}
    page = (await api.get(f"/api/v1/monitors/{monitor_id}/checks", params=params)).json()
    assert len(page["items"]) == 1


async def test_naive_datetimes_are_rejected(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock
) -> None:
    monitor = await create_monitor(sessions, clock)
    response = await api.get(
        f"/api/v1/monitors/{monitor.id}/checks", params={"from": "2026-01-15T12:00:00"}
    )
    assert response.status_code == 422


async def test_pagination_limits(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock
) -> None:
    monitor = await create_monitor(sessions, clock)
    base = f"/api/v1/monitors/{monitor.id}/checks"
    assert (await api.get(base, params={"limit": 0})).status_code == 422
    assert (await api.get(base, params={"limit": 201})).status_code == 422
    assert (await api.get(base, params={"cursor": "lixo!!"})).status_code == 422
    assert (await api.get("/api/v1/incidents", params={"limit": 500})).status_code == 422
    assert (await api.get("/api/v1/incidents", params={"status": "xyz"})).status_code == 422


async def test_incident_list_detail_and_timeline(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    monitor = await create_monitor(sessions, clock, failure_threshold=2, recovery_threshold=1)
    target = ScriptedTarget(clock)
    worker = make_worker(sessions, clock, target, settings)
    for mode in ["error", "error", "ok", "error", "error"]:
        target.mode = mode
        await tick(worker, clock)

    open_page = (await api.get("/api/v1/incidents", params={"status": "open"})).json()
    closed_page = (await api.get("/api/v1/incidents", params={"status": "resolved"})).json()
    assert len(open_page["items"]) == 1 and len(closed_page["items"]) == 1
    assert (await api.get("/api/v1/incidents", params={"monitor_id": monitor.id})).json()["items"][
        0
    ]["status"] == "open"

    resolved_id = closed_page["items"][0]["id"]
    detail = (await api.get(f"/api/v1/incidents/{resolved_id}")).json()
    assert [e["kind"] for e in detail["events"]] == ["first_failure", "opened", "resolved"]
    assert detail["incident"]["opening_reason"].startswith("Incidente confirmado após 2 falhas")
    assert detail["incident"]["resolution_explanation"].startswith(
        "Recuperado após 1 sucesso consecutivo"
    )
    assert detail["events"][1]["details"]["failure_threshold"] == 2
    assert [a["kind"] for a in detail["alerts"]] == ["incident.opened", "incident.resolved"]
    assert (await api.get("/api/v1/incidents/999")).status_code == 404


async def test_alerts_endpoint_lists_deliveries_and_attempts(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    await api.post(
        "/api/v1/destinations", json={"name": "equipe", "url": "https://hooks.example.com/x"}
    )
    await create_monitor(sessions, clock, failure_threshold=1)
    target = ScriptedTarget(clock)
    target.mode = "error"
    worker = make_worker(sessions, clock, target, settings)
    await tick(worker, clock)
    await worker.run_deliveries_once()
    [alert] = (await api.get("/api/v1/alerts")).json()
    assert alert["event_id"] == "incident:1:opened"
    [delivery] = alert["deliveries"]
    assert delivery["status"] == "delivered" and len(delivery["attempts"]) == 1
