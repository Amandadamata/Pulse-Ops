"""Dependencies shared by the routes: application state, database session and login."""

import hmac
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pulseops.clock import Clock
from pulseops.config import Settings
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
    """One session per request. Routes that change data call commit() explicitly;
    anything not committed is rolled back when the session closes."""
    async with state.sessions() as session:
        yield session


Db = Annotated[AsyncSession, Depends(get_db)]


@dataclass(frozen=True)
class AuthContext:
    """Values copied from the session at the start of the request.

    It does not keep ORM objects: if the route rolls back the transaction, loaded objects
    expire, and reading them again in the template would need I/O outside an async
    context (bug B7).
    """

    operator_id: int
    username: str
    csrf_token: str


async def current_auth(request: Request, db: Db, state: State) -> AuthContext | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    loaded = await auth.load_session(db, token, now=state.clock.now())
    if loaded is None:
        return None
    operator_session, operator = loaded
    return AuthContext(
        operator_id=operator.id, username=operator.username, csrf_token=operator_session.csrf_token
    )


MaybeAuth = Annotated[AuthContext | None, Depends(current_auth)]


def tokens_match(expected: str | None, received: str | None) -> bool:
    if not expected or not received:
        return False
    return hmac.compare_digest(expected, received)


async def require_api_auth(request: Request, ctx: MaybeAuth) -> AuthContext:
    """JSON API: 401 without a session; methods that change data require the X-CSRF-Token header."""
    if ctx is None:
        raise HTTPException(status_code=401, detail="authentication required")
    if request.method in UNSAFE_METHODS and not tokens_match(
        ctx.csrf_token, request.headers.get("X-CSRF-Token")
    ):
        raise HTTPException(status_code=403, detail="missing or invalid CSRF token")
    return ctx


ApiAuth = Annotated[AuthContext, Depends(require_api_auth)]


class LoginRequiredError(Exception):
    def __init__(self, next_path: str) -> None:
        self.next_path = next_path


async def require_page_auth(request: Request, ctx: MaybeAuth) -> AuthContext:
    """Pages: without a session, redirect to login (handled in app.py)."""
    if ctx is None:
        raise LoginRequiredError(request.url.path)
    return ctx


PageAuth = Annotated[AuthContext, Depends(require_page_auth)]


def verify_form_csrf(ctx: AuthContext, submitted: str | None) -> None:
    if not tokens_match(ctx.csrf_token, submitted):
        raise HTTPException(status_code=403, detail="missing or invalid CSRF token")
