"""Dependências compartilhadas pelas rotas: estado da aplicação, sessão de banco e login."""

import hmac
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pulseops.clock import Clock
from pulseops.config import Settings
from pulseops.db.models import Operator, OperatorSession
from pulseops.db.session import SessionFactory
from pulseops.security.transport import Resolver
from pulseops.security.url_policy import DestinationPolicy
from pulseops.services import auth

SESSION_COOKIE = "pulseops_session"
LOGIN_CSRF_COOKIE = "pulseops_login_csrf"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass
class AppState:
    settings: Settings
    sessions: SessionFactory
    clock: Clock
    policy: DestinationPolicy
    resolver: Resolver | None = None


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.pulseops
    return state


State = Annotated[AppState, Depends(get_state)]


async def get_db(state: State) -> AsyncIterator[AsyncSession]:
    """Uma sessão por requisição. As rotas que alteram dados chamam commit() explicitamente;
    o que não foi confirmado é desfeito quando a sessão fecha."""
    async with state.sessions() as session:
        yield session


Db = Annotated[AsyncSession, Depends(get_db)]


@dataclass(frozen=True)
class AuthContext:
    operator: Operator
    session: OperatorSession

    @property
    def csrf_token(self) -> str:
        return self.session.csrf_token


async def current_auth(request: Request, db: Db, state: State) -> AuthContext | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    loaded = await auth.load_session(db, token, now=state.clock.now())
    return AuthContext(operator=loaded[1], session=loaded[0]) if loaded else None


MaybeAuth = Annotated[AuthContext | None, Depends(current_auth)]


def tokens_match(expected: str | None, received: str | None) -> bool:
    if not expected or not received:
        return False
    return hmac.compare_digest(expected, received)


async def require_api_auth(request: Request, ctx: MaybeAuth) -> AuthContext:
    """API JSON: 401 sem sessão; métodos que alteram dados exigem o header X-CSRF-Token."""
    if ctx is None:
        raise HTTPException(status_code=401, detail="autenticação necessária")
    if request.method in UNSAFE_METHODS and not tokens_match(
        ctx.csrf_token, request.headers.get("X-CSRF-Token")
    ):
        raise HTTPException(status_code=403, detail="token CSRF ausente ou inválido")
    return ctx


ApiAuth = Annotated[AuthContext, Depends(require_api_auth)]


class LoginRequiredError(Exception):
    def __init__(self, next_path: str) -> None:
        self.next_path = next_path


async def require_page_auth(request: Request, ctx: MaybeAuth) -> AuthContext:
    """Páginas: sem sessão, redireciona para o login (tratado em app.py)."""
    if ctx is None:
        raise LoginRequiredError(request.url.path)
    return ctx


PageAuth = Annotated[AuthContext, Depends(require_page_auth)]


def verify_form_csrf(ctx: AuthContext, submitted: str | None) -> None:
    if not tokens_match(ctx.csrf_token, submitted):
        raise HTTPException(status_code=403, detail="token CSRF ausente ou inválido")
