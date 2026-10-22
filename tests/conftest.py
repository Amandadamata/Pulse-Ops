"""Fixtures compartilhadas.

Os testes de integração usam um PostgreSQL real (nunca SQLite). A URL vem de
PULSEOPS_TEST_DATABASE_URL; o banco de teste é recriado do zero a cada execução
e as migrações do Alembic são aplicadas nele.
"""

import os
import re
from collections.abc import AsyncIterator, Iterator

import httpx
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from pulseops.config import Settings
from pulseops.db.models import Base
from pulseops.db.session import SessionFactory, create_engine, create_session_factory
from pulseops.services.auth import create_operator
from pulseops.web.app import create_app
from tests.support import FakeClock, FakeResolver

TEST_DATABASE_URL = os.environ.get(
    "PULSEOPS_TEST_DATABASE_URL",
    "postgresql+psycopg://pulseops:pulseops@127.0.0.1:5433/pulseops_test",
)
ADMIN_USER, ADMIN_PASSWORD = "operadora", "senha-de-teste-123"


def _recreate_database(url: str) -> None:
    parsed = make_url(url)
    admin_dsn = parsed.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{parsed.database}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{parsed.database}"')


def alembic_config(url: str) -> Config:
    config = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    config.attributes["database_url"] = url
    return config


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    _recreate_database(TEST_DATABASE_URL)
    command.upgrade(alembic_config(TEST_DATABASE_URL), "head")
    yield TEST_DATABASE_URL


@pytest.fixture(scope="session")
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(database_url, pool_size=10)
    yield engine
    await engine.dispose()


@pytest.fixture
async def sessions(engine: AsyncEngine) -> SessionFactory:
    """Banco limpo para cada teste (TRUNCATE em todas as tabelas)."""
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    return create_session_factory(engine)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def resolver() -> FakeResolver:
    return FakeResolver()


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(database_url=database_url, display_timezone="America/Sao_Paulo")


@pytest.fixture
async def app_client(
    settings: Settings, sessions: SessionFactory, clock: FakeClock, resolver: FakeResolver
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, sessions=sessions, clock=clock, resolver=resolver)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


CSRF_FIELD = re.compile(r'name="csrf_token" value="([^"]+)"')


async def login(
    client: httpx.AsyncClient, username: str = ADMIN_USER, password: str = ADMIN_PASSWORD
) -> str:
    """Faz login pelo formulário e devolve o token CSRF da sessão."""
    page = await client.get("/login")
    login_csrf = CSRF_FIELD.search(page.text)
    assert login_csrf
    response = await client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": login_csrf.group(1)},
    )
    assert response.status_code == 303, response.text
    dashboard = await client.get("/")
    token = CSRF_FIELD.search(dashboard.text)
    assert token
    return token.group(1)


@pytest.fixture
async def operator(sessions: SessionFactory, clock: FakeClock) -> None:
    async with sessions.begin() as session:
        await create_operator(session, ADMIN_USER, ADMIN_PASSWORD, now=clock.now())


@pytest.fixture
async def api(app_client: httpx.AsyncClient, operator: None) -> httpx.AsyncClient:
    """Cliente autenticado; o header X-CSRF-Token já vai em todas as requisições."""
    token = await login(app_client)
    app_client.headers["X-CSRF-Token"] = token
    return app_client
