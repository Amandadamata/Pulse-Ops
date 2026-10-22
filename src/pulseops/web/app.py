"""Fábrica da aplicação FastAPI (API JSON + dashboard)."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException as StarletteHTTPException

from pulseops import __version__
from pulseops.clock import Clock, SystemClock
from pulseops.config import Settings
from pulseops.db.session import SessionFactory, create_engine, create_session_factory
from pulseops.logs import configure_logging
from pulseops.security.transport import Resolver
from pulseops.security.url_policy import DestinationPolicy
from pulseops.web import api, health, pages
from pulseops.web.deps import AppState, LoginRequiredError
from pulseops.web.templating import templates

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    settings: Settings | None = None,
    *,
    sessions: SessionFactory | None = None,
    clock: Clock | None = None,
    resolver: Resolver | None = None,
) -> FastAPI:
    """Os testes passam `sessions`, `clock` e `resolver`; em produção tudo vem das variáveis."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = None
        factory = sessions
        if factory is None:
            configure_logging(settings.log_level)
            engine = create_engine(settings.database_url)
            factory = create_session_factory(engine)
        app.state.pulseops = AppState(
            settings=settings,
            sessions=factory,
            clock=clock or SystemClock(),
            policy=DestinationPolicy(settings.allowed_port_set, settings.demo_allowlist),
            resolver=resolver,
        )
        yield
        if engine is not None:
            await engine.dispose()

    app = FastAPI(
        title="PulseOps",
        version=__version__,
        lifespan=lifespan,
        # A documentação interativa fica desligada: a API é de uso do próprio operador.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(health.router)
    app.include_router(api.router)
    app.include_router(pages.router)

    @app.exception_handler(LoginRequiredError)
    async def login_redirect(request: Request, exc: LoginRequiredError) -> Response:
        return RedirectResponse(f"/login?next={quote(exc.next_path)}", status_code=303)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> Response:
        """Na API, JSON; nas páginas, uma página de erro legível (sem detalhes internos)."""
        if request.url.path.startswith(("/api/", "/health/")):
            return JSONResponse(
                {"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers
            )
        titles = {403: "Acesso negado", 404: "Página não encontrada", 409: "Operação não permitida"}
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "title": titles.get(exc.status_code, "Erro"),
                "message": str(exc.detail),
                "tz": settings.timezone,
                "tz_name": settings.display_timezone,
                "demo_mode": settings.demo_mode,
            },
            status_code=exc.status_code,
        )

    @app.exception_handler(DBAPIError)
    async def database_unavailable(request: Request, exc: DBAPIError) -> Response:
        logger.error("erro de banco ao atender requisição", extra={"path": request.url.path})
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "banco de dados indisponível"}, status_code=503)
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "title": "Banco de dados indisponível",
                "message": "Tente novamente em instantes.",
                "tz": settings.timezone,
                "tz_name": settings.display_timezone,
                "demo_mode": settings.demo_mode,
            },
            status_code=503,
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "frame-ancestors 'none'; form-action 'self'",
        )
        return response

    return app
