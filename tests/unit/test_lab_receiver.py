"""Receptor do laboratório: deduplicação por id de evento (cenário 17, lado do destino)."""

import httpx
import pytest

from lab import receiver


@pytest.fixture
async def client():
    receiver.inbox.__init__()  # estado limpo a cada teste
    transport = httpx.ASGITransport(app=receiver.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://lab") as c:
        yield c


async def test_duplicate_event_is_detected(client: httpx.AsyncClient) -> None:
    headers = {"X-PulseOps-Event-Id": "incident:7:opened"}
    first = await client.post("/webhook", json={"type": "incident.opened"}, headers=headers)
    second = await client.post("/webhook", json={"type": "incident.opened"}, headers=headers)
    assert first.json() == {"duplicate": False}
    assert second.json() == {"duplicate": True}
    state = (await client.get("/control/received")).json()
    assert state["event_ids"] == ["incident:7:opened"] and state["duplicates"] == 1


async def test_unavailable_receiver_rejects_then_accepts(client: httpx.AsyncClient) -> None:
    await client.post("/control/availability", json={"available": False})
    headers = {"X-PulseOps-Event-Id": "incident:8:opened"}
    assert (await client.post("/webhook", json={}, headers=headers)).status_code == 503
    await client.post("/control/availability", json={"available": True})
    assert (await client.post("/webhook", json={}, headers=headers)).status_code == 200
    assert (await client.get("/control/received")).json()["rejected"] == 1


async def test_missing_event_id_is_rejected(client: httpx.AsyncClient) -> None:
    assert (await client.post("/webhook", json={})).status_code == 400
