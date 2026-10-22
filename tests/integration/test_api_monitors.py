"""API de monitores (RF01): cenários 1, 11 e 20."""

import httpx
import pytest
from sqlalchemy import func, select

from pulseops.config import Settings
from pulseops.db.models import Check, Incident
from pulseops.db.session import SessionFactory
from tests.support import FakeClock, ScriptedTarget
from tests.support_db import make_worker, tick

VALID = {"name": "Checkout", "url": "https://checkout.example.com/health"}


async def test_create_list_get_update(api: httpx.AsyncClient) -> None:
    created = await api.post("/api/v1/monitors", json={**VALID, "description": "fluxo de compra"})
    assert created.status_code == 201
    monitor_id = created.json()["id"]
    assert [m["name"] for m in (await api.get("/api/v1/monitors")).json()] == ["Checkout"]

    updated = await api.put(
        f"/api/v1/monitors/{monitor_id}",
        json={**VALID, "name": "Checkout v2", "interval_seconds": 120},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert (body["name"], body["interval_seconds"], body["config_version"]) == (
        "Checkout v2",
        120,
        1,
    )

    changed = await api.put(
        f"/api/v1/monitors/{monitor_id}", json={**VALID, "failure_threshold": 5}
    )
    assert changed.json()["config_version"] == 2


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({**VALID, "url": "ftp://x.example.com"}, "url"),
        ({**VALID, "url": "http://user:pw@x.example.com"}, "url"),
        ({**VALID, "url": "http://127.0.0.1/"}, "url"),
        ({**VALID, "url": "http://169.254.169.254/latest/meta-data"}, "url"),
        ({**VALID, "url": "https://x.example.com:5432/"}, "url"),
        ({**VALID, "timeout_seconds": 60, "interval_seconds": 60}, "timeout_seconds"),
        ({**VALID, "latency_threshold_ms": 9000, "timeout_seconds": 5}, "latency_threshold_ms"),
        ({**VALID, "accepted_status_codes": "299-200"}, "accepted_status_codes"),
        ({**VALID, "interval_seconds": 5}, "interval_seconds"),
    ],
)
async def test_invalid_configuration_is_rejected(
    api: httpx.AsyncClient, body: dict, field: str
) -> None:
    """Cenário 1."""
    response = await api.post("/api/v1/monitors", json=body)
    assert response.status_code == 422
    assert field in [d["loc"][-1] for d in response.json()["detail"]]


async def test_unknown_fields_and_methods_rejected(api: httpx.AsyncClient) -> None:
    assert (
        await api.post("/api/v1/monitors", json={**VALID, "headers": {"a": "b"}})
    ).status_code == 422
    assert (await api.post("/api/v1/monitors", json={**VALID, "method": "POST"})).status_code == 422


async def test_duplicate_name_is_rejected_case_insensitive(api: httpx.AsyncClient) -> None:
    assert (await api.post("/api/v1/monitors", json=VALID)).status_code == 201
    response = await api.post("/api/v1/monitors", json={**VALID, "name": "CHECKOUT"})
    assert response.status_code == 422


async def test_dns_pointing_to_private_address_is_rejected(
    api: httpx.AsyncClient, resolver
) -> None:
    resolver.mapping["interno.example.com"] = ["10.1.2.3"]
    response = await api.post(
        "/api/v1/monitors", json={**VALID, "url": "https://interno.example.com/"}
    )
    assert response.status_code == 422
    assert "endereço privado" in response.json()["detail"][0]["msg"]


async def test_pause_resume_and_conflicts(api: httpx.AsyncClient) -> None:
    """Cenário 11 pela API."""
    monitor_id = (await api.post("/api/v1/monitors", json=VALID)).json()["id"]
    paused = (await api.post(f"/api/v1/monitors/{monitor_id}/pause")).json()
    assert (paused["state"], paused["health"], paused["next_run_at"]) == ("paused", "paused", None)
    assert (await api.post(f"/api/v1/monitors/{monitor_id}/pause")).status_code == 409
    resumed = (await api.post(f"/api/v1/monitors/{monitor_id}/resume")).json()
    assert (resumed["state"], resumed["health"]) == ("active", "no_data")
    assert (await api.post(f"/api/v1/monitors/{monitor_id}/explode")).status_code == 404
    assert (await api.post("/api/v1/monitors/999/pause")).status_code == 404


async def test_archive_preserves_history(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    """Cenário 20: arquivar não apaga checks nem incidentes."""
    body = {**VALID, "failure_threshold": 1}
    monitor_id = (await api.post("/api/v1/monitors", json=body)).json()["id"]
    target = ScriptedTarget(clock)
    target.mode = "error"
    worker = make_worker(sessions, clock, target, settings)
    await tick(worker, clock)
    await tick(worker, clock)

    archived = (await api.post(f"/api/v1/monitors/{monitor_id}/archive")).json()
    assert archived["state"] == "archived" and archived["archived_at"]
    assert (await api.put(f"/api/v1/monitors/{monitor_id}", json=body)).status_code == 409
    assert (await api.post(f"/api/v1/monitors/{monitor_id}/resume")).status_code == 409

    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Check)) == 2
        incident = (await session.scalars(select(Incident))).one()
    assert (incident.status, incident.resolution_reason) == ("closed", "monitor_archived")

    checks = (await api.get(f"/api/v1/monitors/{monitor_id}/checks")).json()
    assert len(checks["items"]) == 2
    assert monitor_id not in [m["id"] for m in (await api.get("/api/v1/monitors")).json()]
    listed = (await api.get("/api/v1/monitors", params={"include_archived": True})).json()
    assert monitor_id in [m["id"] for m in listed]
    assert await tick(worker, clock) == 0  # arquivado não é mais verificado

    # O nome volta a ficar livre para um monitor novo.
    assert (await api.post("/api/v1/monitors", json=VALID)).status_code == 201


async def test_check_now_marks_next_check_as_manual(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    monitor_id = (await api.post("/api/v1/monitors", json=VALID)).json()["id"]
    worker = make_worker(sessions, clock, ScriptedTarget(clock), settings)
    await tick(worker, clock, 5)
    assert await worker.run_checks_once() == 0  # próximo só daqui a 55 s
    await api.post(f"/api/v1/monitors/{monitor_id}/check")
    assert await worker.run_checks_once() == 1
    items = (await api.get(f"/api/v1/monitors/{monitor_id}/checks")).json()["items"]
    assert [c["trigger"] for c in items] == ["manual", "scheduled"]


async def test_destinations_api_validates_url(api: httpx.AsyncClient) -> None:
    bad = await api.post(
        "/api/v1/destinations", json={"name": "interno", "url": "http://192.168.0.10/hook"}
    )
    assert bad.status_code == 422
    good = await api.post(
        "/api/v1/destinations", json={"name": "equipe", "url": "https://hooks.example.com/x"}
    )
    assert good.status_code == 201
    dest_id = good.json()["id"]
    assert (
        await api.post(
            "/api/v1/destinations", json={"name": "equipe", "url": "https://hooks.example.com/y"}
        )
    ).status_code == 409
    patched = await api.patch(f"/api/v1/destinations/{dest_id}", json={"enabled": False})
    assert patched.json()["enabled"] is False
