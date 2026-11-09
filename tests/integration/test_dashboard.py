"""Interface in the main flows (RF07) and scenario 23 (injection in the interface)."""

import re

import httpx

from pulseops.config import Settings
from pulseops.db.session import SessionFactory
from pulseops.web.app import create_app
from tests.support import FakeClock, FakeResolver, ScriptedTarget
from tests.support_db import create_monitor, make_worker, tick

CSRF = re.compile(r'name="csrf_token" value="([^"]+)"')


async def test_empty_state(api: httpx.AsyncClient) -> None:
    page = await api.get("/")
    assert page.status_code == 200
    assert "No monitors yet" in page.text
    assert "No signal from the worker" in page.text


async def test_create_monitor_through_form_and_see_errors(api: httpx.AsyncClient) -> None:
    form = await api.get("/monitors/new")
    token = CSRF.search(form.text)
    assert token
    data = {
        "csrf_token": token.group(1),
        "name": "Search",
        "url": "http://127.0.0.1:8080/",
        "method": "GET",
        "interval_seconds": "10",
        "timeout_seconds": "5",
        "latency_threshold_ms": "abc",
        "failure_threshold": "3",
        "recovery_threshold": "2",
        "accepted_status_codes": "200-299",
    }
    bad = await api.post("/monitors/new", data=data)
    assert bad.status_code == 422 and "enter a whole number" in bad.text

    data["latency_threshold_ms"] = "800"
    bad = await api.post("/monitors/new", data=data)
    assert bad.status_code == 422
    assert "loopback address" in bad.text and "must be between 30 and 86400" in bad.text
    assert 'aria-invalid="true"' in bad.text

    data.update(url="https://search.example.com/health", interval_seconds="60")
    ok = await api.post("/monitors/new", data=data)
    assert ok.status_code == 303
    detail = await api.get(ok.headers["location"])
    assert "Search" in detail.text and "No data: no check finished yet" in detail.text


async def test_monitor_detail_with_real_data(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    monitor = await create_monitor(sessions, clock, failure_threshold=2)
    target = ScriptedTarget(clock)
    worker = make_worker(sessions, clock, target, settings)
    await worker.heartbeat()
    for mode in ["ok", "slow", "error", "error"]:
        target.mode = mode
        await tick(worker, clock, 60)
    await worker.heartbeat()
    page = await api.get(f"/monitors/{monitor.id}")
    text = page.text
    assert "<svg" in text and "4 checks" in text  # chart generated from the saved checks
    assert "Incident confirmed after 2 consecutive failures" in text
    assert "Down" in text and "Unexpected status" in text and "Slow" in text
    assert "p95 (n = 4)" in text
    filtered = await api.get(f"/monitors/{monitor.id}", params={"outcome": "slow"})
    assert filtered.text.count('class="badge badge-outcome-slow"') == 1


async def test_incident_pages_and_notifications(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    await api.post(
        "/api/v1/destinations", json={"name": "team", "url": "https://hooks.example.com/x"}
    )
    await create_monitor(sessions, clock, failure_threshold=1)
    target = ScriptedTarget(clock)
    target.mode = "timeout"
    worker = make_worker(sessions, clock, target, settings)
    await tick(worker, clock)
    listing = await api.get("/incidents")
    assert (
        "Incident confirmed after 1 consecutive failure; last result: no response in 5 s."
        in listing.text
    )
    detail = await api.get("/incidents/1")
    assert "First failure" in detail.text and "incident:1:opened" in detail.text
    await worker.run_deliveries_once()
    notifications = await api.get("/notifications")
    assert "Delivered" in notifications.text and "at least once" in notifications.text


async def test_monitor_name_is_escaped(api: httpx.AsyncClient) -> None:
    """Scenario 23: HTML/JS in the name and description shows up as text."""
    payload = '<script>alert("x")</script><img src=x onerror=alert(1)>'
    created = await api.post(
        "/api/v1/monitors",
        json={"name": payload[:100], "description": payload, "url": "https://x.example.com/?q=<b>"},
    )
    assert created.status_code == 201
    for path in (
        "/",
        f"/monitors/{created.json()['id']}",
        f"/monitors/{created.json()['id']}/edit",
    ):
        page = await api.get(path)
        assert "<script>alert" not in page.text
        assert "<img src=x" not in page.text
        assert "&lt;script&gt;" in page.text


async def test_sql_injection_attempts_are_plain_data(api: httpx.AsyncClient) -> None:
    """Scenario 23: text with SQL is saved and shown as data; invalid filters give 422."""
    name = "x'); DROP TABLE monitors; --"
    created = await api.post(
        "/api/v1/monitors", json={"name": name, "url": "https://x.example.com/"}
    )
    assert created.status_code == 201
    assert (await api.get(f"/api/v1/monitors/{created.json()['id']}")).json()["name"] == name
    monitor_id = created.json()["id"]
    bad_filter = await api.get(f"/api/v1/monitors/{monitor_id}/checks?outcome=x' OR '1'='1")
    assert bad_filter.status_code == 422
    bad_status = await api.get("/api/v1/incidents?status=open' OR 1=1 --")
    assert bad_status.status_code == 422
    bad_cursor = await api.get(f"/api/v1/monitors/{monitor_id}/checks?cursor=1;DROP")
    assert bad_cursor.status_code == 422
    assert [m["name"] for m in (await api.get("/api/v1/monitors")).json()] == [name]


async def test_security_headers(api: httpx.AsyncClient) -> None:
    response = await api.get("/")
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY"


async def test_not_found_page_is_html(api: httpx.AsyncClient) -> None:
    response = await api.get("/monitors/999")
    assert response.status_code == 404 and "Page not found" in response.text


async def test_demo_banner_only_in_demo_mode(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    demo = settings.model_copy(update={"demo_mode": True})
    app = create_app(demo, sessions=sessions, clock=clock, resolver=FakeResolver())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client,
    ):
        assert "Demo mode" in (await client.get("/login")).text
    normal = create_app(settings, sessions=sessions, clock=clock, resolver=FakeResolver())
    async with (
        normal.router.lifespan_context(normal),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=normal), base_url="http://t") as client,
    ):
        assert "Demo mode" not in (await client.get("/login")).text


async def test_times_are_shown_in_display_timezone(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    """Scenario 18 in the interface: 12:00 UTC shows as 09:00 in Sao Paulo."""
    monitor = await create_monitor(sessions, clock)
    await make_worker(sessions, clock, ScriptedTarget(clock), settings).run_checks_once()
    page = await api.get(f"/monitors/{monitor.id}")
    assert "15/01/2026 09:00:00" in page.text
    assert "America/Sao_Paulo" in page.text


def _form_of(monitor: dict[str, object], token: str, **changes: object) -> dict[str, str]:
    fields = (
        "name",
        "description",
        "url",
        "method",
        "interval_seconds",
        "timeout_seconds",
        "accepted_status_codes",
        "latency_threshold_ms",
        "failure_threshold",
        "recovery_threshold",
    )
    data = {f: str(monitor[f]) for f in fields}
    data.update({k: str(v) for k, v in changes.items()})
    data["csrf_token"] = token
    return data


async def test_edit_and_lifecycle_actions_through_forms(api: httpx.AsyncClient) -> None:
    """RF01 through the interface: edit, pause, resume, check now and archive."""
    monitor = (
        await api.post("/api/v1/monitors", json={"name": "Store", "url": "https://x.example.com/"})
    ).json()
    path = f"/monitors/{monitor['id']}"
    edit = await api.get(f"{path}/edit")
    token = CSRF.search(edit.text)
    assert token and 'value="Store"' in edit.text
    csrf = token.group(1)

    invalid = await api.post(f"{path}/edit", data=_form_of(monitor, csrf, failure_threshold=0))
    assert invalid.status_code == 422 and "Store" in invalid.text
    saved = await api.post(f"{path}/edit", data=_form_of(monitor, csrf, name="Online store"))
    assert saved.status_code == 303 and saved.headers["location"] == path
    assert "Online store" in (await api.get(path)).text

    for action, label in [("pause", "Paused"), ("resume", "Active"), ("check", "Active")]:
        response = await api.post(f"{path}/{action}", data={"csrf_token": csrf})
        assert response.status_code == 303, action
        assert label in (await api.get(path)).text
    assert (await api.post(f"{path}/desconhecida", data={"csrf_token": csrf})).status_code == 404
    assert (await api.post(f"{path}/archive", data={"csrf_token": csrf})).status_code == 303
    assert (await api.post(f"{path}/pause", data={"csrf_token": csrf})).status_code == 409
    archived_edit = await api.post(f"{path}/edit", data=_form_of(monitor, csrf, name="Another"))
    assert archived_edit.status_code == 409
    assert (await api.get("/monitors/9999/edit")).status_code == 404


async def test_destination_form_validates_and_toggles(api: httpx.AsyncClient) -> None:
    page = await api.get("/notifications")
    token = CSRF.search(page.text)
    assert token
    csrf = token.group(1)
    form = "/notifications/destinations"

    blocked = await api.post(
        form, data={"csrf_token": csrf, "name": "Internal", "url": "http://10.0.0.5/hook"}
    )
    assert blocked.status_code == 422 and "10.0.0.5" in blocked.text  # valor preenchido volta
    unnamed = await api.post(
        form, data={"csrf_token": csrf, "name": "", "url": "https://h.example.com/"}
    )
    assert unnamed.status_code == 422 and "required" in unnamed.text

    ok = {"csrf_token": csrf, "name": "Team", "url": "https://hooks.example.com/pulse"}
    assert (await api.post(form, data=ok)).status_code == 303
    duplicate = await api.post(form, data=ok)
    assert (
        duplicate.status_code == 422
        and "a destination with this name already exists" in duplicate.text
    )

    [destination] = (await api.get("/api/v1/destinations")).json()
    toggle = f"{form}/{destination['id']}/toggle"
    assert (await api.post(toggle, data={"csrf_token": csrf})).status_code == 303
    assert "Disabled" in (await api.get("/notifications")).text
    assert (await api.post(f"{form}/9999/toggle", data={"csrf_token": csrf})).status_code == 404
    assert (await api.post(toggle, data={"csrf_token": "wrong"})).status_code == 403
