"""Cenário 21: autenticação, autorização e CSRF (RF08)."""

import hashlib
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from pulseops.db.models import OperatorSession
from pulseops.db.session import SessionFactory
from tests.conftest import ADMIN_PASSWORD, ADMIN_USER, CSRF_FIELD
from tests.support import FakeClock

PROTECTED_GETS = [
    "/api/v1/monitors",
    "/api/v1/summary",
    "/api/v1/incidents",
    "/api/v1/alerts",
    "/api/v1/destinations",
    "/api/v1/monitors/1/checks",
    "/api/v1/monitors/1/metrics",
]
PROTECTED_PAGES = ["/", "/monitors/new", "/incidents", "/notifications", "/monitors/1"]


@pytest.mark.parametrize("path", PROTECTED_GETS)
async def test_api_requires_session(app_client: httpx.AsyncClient, path: str) -> None:
    assert (await app_client.get(path)).status_code == 401


@pytest.mark.parametrize("path", PROTECTED_PAGES)
async def test_pages_redirect_to_login(app_client: httpx.AsyncClient, path: str) -> None:
    response = await app_client.get(path)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=")


async def test_mutations_without_session_are_rejected(app_client: httpx.AsyncClient) -> None:
    assert (await app_client.post("/api/v1/monitors", json={})).status_code == 401
    assert (await app_client.post("/api/v1/monitors/1/pause")).status_code == 401
    assert (await app_client.post("/api/v1/destinations", json={})).status_code == 401
    assert (await app_client.post("/monitors/1/pause", data={"csrf_token": "x"})).status_code == 303


async def test_health_endpoints_are_public(app_client: httpx.AsyncClient) -> None:
    assert (await app_client.get("/health/live")).status_code == 200


async def test_wrong_password_is_rejected(app_client: httpx.AsyncClient, operator: None) -> None:
    page = await app_client.get("/login")
    token = CSRF_FIELD.search(page.text)
    assert token
    response = await app_client.post(
        "/login",
        data={"username": ADMIN_USER, "password": "errada-errada", "csrf_token": token.group(1)},
    )
    assert response.status_code == 401
    assert "Usuário ou senha inválidos" in response.text
    assert "pulseops_session" not in response.cookies


async def test_unknown_user_gets_same_message(
    app_client: httpx.AsyncClient, operator: None
) -> None:
    page = await app_client.get("/login")
    token = CSRF_FIELD.search(page.text)
    assert token
    response = await app_client.post(
        "/login",
        data={"username": "ninguem", "password": ADMIN_PASSWORD, "csrf_token": token.group(1)},
    )
    assert response.status_code == 401 and "Usuário ou senha inválidos" in response.text


async def test_login_form_requires_its_csrf_cookie(
    app_client: httpx.AsyncClient, operator: None
) -> None:
    response = await app_client.post(
        "/login", data={"username": ADMIN_USER, "password": ADMIN_PASSWORD, "csrf_token": "forjado"}
    )
    assert response.status_code == 403


async def test_session_cookie_flags(app_client: httpx.AsyncClient, operator: None) -> None:
    page = await app_client.get("/login")
    token = CSRF_FIELD.search(page.text)
    assert token
    response = await app_client.post(
        "/login",
        data={"username": ADMIN_USER, "password": ADMIN_PASSWORD, "csrf_token": token.group(1)},
    )
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "max-age=28800" in cookie


async def test_api_mutation_requires_csrf_header(api: httpx.AsyncClient) -> None:
    body = {"name": "x", "url": "https://x.example.com"}
    good = api.headers.pop("X-CSRF-Token")
    assert (await api.post("/api/v1/monitors", json=body)).status_code == 403
    assert (
        await api.post("/api/v1/monitors", json=body, headers={"X-CSRF-Token": "errado"})
    ).status_code == 403
    assert (
        await api.post("/api/v1/monitors", json=body, headers={"X-CSRF-Token": good})
    ).status_code == 201


async def test_form_action_requires_csrf_field(api: httpx.AsyncClient) -> None:
    created = (
        await api.post("/api/v1/monitors", json={"name": "x", "url": "https://x.example.com"})
    ).json()
    api.headers.pop("X-CSRF-Token")
    assert (await api.post(f"/monitors/{created['id']}/pause", data={})).status_code == 422
    assert (
        await api.post(f"/monitors/{created['id']}/pause", data={"csrf_token": "x"})
    ).status_code == 403


async def test_logout_invalidates_session(api: httpx.AsyncClient) -> None:
    token = api.headers["X-CSRF-Token"]
    old_cookie = api.cookies.get("pulseops_session")
    response = await api.post("/logout", data={"csrf_token": token})
    assert response.status_code == 303
    api.cookies.set("pulseops_session", old_cookie or "")  # reusar o cookie antigo não funciona
    assert (await api.get("/api/v1/monitors")).status_code == 401


async def test_session_expires(api: httpx.AsyncClient, clock: FakeClock) -> None:
    assert (await api.get("/api/v1/monitors")).status_code == 200
    clock.advance(timedelta(minutes=481).total_seconds())
    assert (await api.get("/api/v1/monitors")).status_code == 401


async def test_session_token_is_stored_hashed(
    api: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    token = api.cookies.get("pulseops_session")
    assert token
    async with sessions() as session:
        stored = list(await session.scalars(select(OperatorSession.token_hash)))
    assert stored == [hashlib.sha256(token.encode()).hexdigest()]
    assert token not in stored


async def test_next_parameter_cannot_redirect_outside(
    app_client: httpx.AsyncClient, operator: None
) -> None:
    page = await app_client.get("/login?next=//evil.example.com")
    token = CSRF_FIELD.search(page.text)
    assert token
    response = await app_client.post(
        "/login",
        data={
            "username": ADMIN_USER,
            "password": ADMIN_PASSWORD,
            "csrf_token": token.group(1),
            "next": "https://evil.example.com",
        },
    )
    assert response.headers["location"] == "/"


async def test_javascript_has_no_token(app_client: httpx.AsyncClient) -> None:
    script = (await app_client.get("/static/app.js")).text
    assert "csrf" not in script.lower() and "token" not in script.lower().replace(
        "nenhum token", ""
    )


async def test_login_page_redirects_when_already_logged_in(api: httpx.AsyncClient) -> None:
    response = await api.get("/login")
    assert response.status_code == 303 and response.headers["location"] == "/"
