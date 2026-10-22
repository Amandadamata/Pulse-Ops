"""RF09: liveness e readiness."""

import httpx

from pulseops.config import Settings
from pulseops.db.session import create_engine, create_session_factory
from pulseops.web.app import create_app
from tests.support import FakeClock


async def test_live_and_ready(app_client: httpx.AsyncClient) -> None:
    assert (await app_client.get("/health/live")).json() == {"status": "ok"}
    ready = await app_client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok" and ready.json()["worker"]["alive"] is False


async def test_ready_returns_503_when_database_is_down(
    settings: Settings, clock: FakeClock
) -> None:
    dead = create_engine("postgresql+psycopg://pulseops:x@127.0.0.1:1/nada", pool_size=1)
    app = create_app(settings, sessions=create_session_factory(dead), clock=clock)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client,
    ):
        assert (await client.get("/health/live")).status_code == 200
        ready = await client.get("/health/ready")
        assert ready.status_code == 503 and ready.json()["database"] == "unavailable"
    await dead.dispose()
