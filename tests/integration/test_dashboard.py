"""Interface nos fluxos principais (RF07) e cenário 23 (injeção na interface)."""

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
    assert "Nenhum monitor cadastrado" in page.text
    assert "Nenhum sinal do worker" in page.text


async def test_create_monitor_through_form_and_see_errors(api: httpx.AsyncClient) -> None:
    form = await api.get("/monitors/new")
    token = CSRF.search(form.text)
    assert token
    data = {
        "csrf_token": token.group(1),
        "name": "Busca",
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
    assert bad.status_code == 422 and "informe um número inteiro" in bad.text

    data["latency_threshold_ms"] = "800"
    bad = await api.post("/monitors/new", data=data)
    assert bad.status_code == 422
    assert "endereço de loopback" in bad.text and "deve estar entre 30 e 86400" in bad.text
    assert 'aria-invalid="true"' in bad.text

    data.update(url="https://busca.example.com/health", interval_seconds="60")
    ok = await api.post("/monitors/new", data=data)
    assert ok.status_code == 303
    detail = await api.get(ok.headers["location"])
    assert "Busca" in detail.text and "Sem dados: nenhum check concluído ainda" in detail.text


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
    assert "<svg" in text and "4 checks" in text  # gráfico gerado dos checks gravados
    assert "Incidente confirmado após 2 falhas consecutivas" in text
    assert "Indisponível" in text and "Status inesperado" in text and "Lento" in text
    assert "p95 (n = 4)" in text
    filtered = await api.get(f"/monitors/{monitor.id}", params={"outcome": "slow"})
    assert filtered.text.count('class="badge badge-outcome-slow"') == 1


async def test_incident_pages_and_notifications(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    await api.post(
        "/api/v1/destinations", json={"name": "equipe", "url": "https://hooks.example.com/x"}
    )
    await create_monitor(sessions, clock, failure_threshold=1)
    target = ScriptedTarget(clock)
    target.mode = "timeout"
    worker = make_worker(sessions, clock, target, settings)
    await tick(worker, clock)
    listing = await api.get("/incidents")
    assert (
        "Incidente confirmado após 1 falha consecutiva; último resultado: sem resposta em 5 s."
        in listing.text
    )
    detail = await api.get("/incidents/1")
    assert "Primeira falha" in detail.text and "incident:1:opened" in detail.text
    await worker.run_deliveries_once()
    notifications = await api.get("/notifications")
    assert "Entregue" in notifications.text and "pelo menos uma vez" in notifications.text


async def test_monitor_name_is_escaped(api: httpx.AsyncClient) -> None:
    """Cenário 23: HTML/JS no nome e na descrição aparece como texto."""
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


async def test_security_headers(api: httpx.AsyncClient) -> None:
    response = await api.get("/")
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY"


async def test_not_found_page_is_html(api: httpx.AsyncClient) -> None:
    response = await api.get("/monitors/999")
    assert response.status_code == 404 and "Página não encontrada" in response.text


async def test_demo_banner_only_in_demo_mode(
    sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    demo = settings.model_copy(update={"demo_mode": True})
    app = create_app(demo, sessions=sessions, clock=clock, resolver=FakeResolver())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client,
    ):
        assert "Modo demonstração" in (await client.get("/login")).text
    normal = create_app(settings, sessions=sessions, clock=clock, resolver=FakeResolver())
    async with (
        normal.router.lifespan_context(normal),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=normal), base_url="http://t") as client,
    ):
        assert "Modo demonstração" not in (await client.get("/login")).text


async def test_times_are_shown_in_display_timezone(
    api: httpx.AsyncClient, sessions: SessionFactory, clock: FakeClock, settings: Settings
) -> None:
    """Cenário 18 na interface: 12:00 UTC aparece como 09:00 em São Paulo."""
    monitor = await create_monitor(sessions, clock)
    await make_worker(sessions, clock, ScriptedTarget(clock), settings).run_checks_once()
    page = await api.get(f"/monitors/{monitor.id}")
    assert "15/01/2026 09:00:00" in page.text
    assert "America/Sao_Paulo" in page.text
