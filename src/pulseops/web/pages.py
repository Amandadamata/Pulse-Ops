"""Páginas do dashboard (RF07) e login/logout (RF08)."""

import secrets
from datetime import timedelta
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pulseops.db.models import AlertDestination
from pulseops.domain.monitor_rules import FieldError, MonitorConfig
from pulseops.domain.outcomes import Outcome
from pulseops.security.transport import validate_destination
from pulseops.security.url_policy import UnsafeDestinationError
from pulseops.services import auth, queries
from pulseops.services import monitors as monitor_service
from pulseops.services.errors import ConflictError, NotFoundError, ValidationFailedError
from pulseops.web.charts import build_latency_chart
from pulseops.web.deps import (
    LOGIN_CSRF_COOKIE,
    SESSION_COOKIE,
    AuthContext,
    Db,
    MaybeAuth,
    PageAuth,
    State,
    tokens_match,
    verify_form_csrf,
)
from pulseops.web.templating import templates

router = APIRouter(include_in_schema=False)

WINDOWS = {"1h": timedelta(hours=1), "24h": timedelta(hours=24), "7d": timedelta(days=7)}
Csrf = Annotated[str, Form()]


def render(
    request: Request,
    state: State,
    template: str,
    ctx: AuthContext | None,
    status_code: int = 200,
    **context: Any,
) -> HTMLResponse:
    base = {
        "tz": state.settings.timezone,
        "tz_name": state.settings.display_timezone,
        "demo_mode": state.settings.demo_mode,
        "operator": ctx.operator if ctx else None,
        "csrf_token": ctx.csrf_token if ctx else None,
    }
    return templates.TemplateResponse(
        request, template, {**base, **context}, status_code=status_code
    )


def redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def _safe_next(path: str | None) -> str:
    """Só aceita caminhos internos no ?next=, para o login não virar um redirecionador aberto."""
    if not path or not path.startswith("/") or path.startswith("//") or urlsplit(path).netloc:
        return "/"
    return path


# ---- login -------------------------------------------------------------------------


@router.get("/login")
async def login_form(request: Request, state: State, ctx: MaybeAuth, next: str = "/") -> Response:
    if ctx is not None:
        return redirect(_safe_next(next))
    token = secrets.token_urlsafe(32)
    response = render(request, state, "login.html", None, login_csrf=token, next=_safe_next(next))
    response.set_cookie(
        LOGIN_CSRF_COOKIE,
        token,
        httponly=True,
        samesite="strict",
        secure=state.settings.cookie_secure,
    )
    return response


@router.post("/login")
async def login(
    request: Request,
    db: Db,
    state: State,
    username: Annotated[str, Form(max_length=50)],
    password: Annotated[str, Form(max_length=1024)],
    csrf_token: Csrf,
    next: Annotated[str, Form()] = "/",
) -> Response:
    if not tokens_match(request.cookies.get(LOGIN_CSRF_COOKIE), csrf_token):
        raise HTTPException(403, "token CSRF ausente ou inválido")
    operator = await auth.authenticate(db, username, password)
    if operator is None:
        token = secrets.token_urlsafe(32)
        response = render(
            request,
            state,
            "login.html",
            None,
            status_code=401,
            error="Usuário ou senha inválidos.",
            login_csrf=token,
            next=_safe_next(next),
        )
        response.set_cookie(
            LOGIN_CSRF_COOKIE,
            token,
            httponly=True,
            samesite="strict",
            secure=state.settings.cookie_secure,
        )
        return response
    ttl = timedelta(minutes=state.settings.session_ttl_minutes)
    new = await auth.start_session(db, operator, now=state.clock.now(), ttl=ttl)
    await db.commit()
    success = redirect(_safe_next(next))
    success.set_cookie(
        SESSION_COOKIE,
        new.token,
        max_age=int(ttl.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=state.settings.cookie_secure,
        path="/",
    )
    success.delete_cookie(LOGIN_CSRF_COOKIE)
    return success


@router.post("/logout")
async def logout(request: Request, db: Db, ctx: PageAuth, csrf_token: Csrf) -> Response:
    verify_form_csrf(ctx, csrf_token)
    await auth.end_session(db, request.cookies.get(SESSION_COOKIE, ""))
    await db.commit()
    response = redirect("/login")
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


# ---- painel e monitores ---------------------------------------------------------


@router.get("/")
async def dashboard(
    request: Request, db: Db, state: State, ctx: PageAuth, archived: bool = False
) -> Response:
    now = state.clock.now()
    worker = await queries.worker_status(
        db, now=now, stale_after=state.settings.worker_stale_after_seconds
    )
    monitors = await queries.list_monitors(db, include_archived=archived)
    rows = [(m, queries.is_stale(m, now=now, worker=worker)) for m in monitors]
    return render(
        request,
        state,
        "dashboard.html",
        ctx,
        summary=await queries.summary(db, now=now, worker=worker),
        worker=worker,
        rows=rows,
        show_archived=archived,
    )


def _form_config(form: dict[str, str]) -> tuple[MonitorConfig | None, list[FieldError]]:
    errors: list[FieldError] = []
    numbers: dict[str, int] = {}
    for field in (
        "interval_seconds",
        "timeout_seconds",
        "latency_threshold_ms",
        "failure_threshold",
        "recovery_threshold",
    ):
        try:
            numbers[field] = int(form.get(field, ""))
        except ValueError:
            errors.append(FieldError(field, "informe um número inteiro"))
    if errors:
        return None, errors
    return (
        MonitorConfig(
            name=form.get("name", "")[:200],
            url=form.get("url", "")[:3000],
            description=form.get("description", "")[:1000],
            method=form.get("method", "GET"),
            accepted_status_codes=form.get("accepted_status_codes", "")[:200],
            **numbers,
        ),
        [],
    )


async def _read_form(request: Request) -> dict[str, str]:
    form = await request.form()
    return {k: v for k, v in form.items() if isinstance(v, str)}


@router.get("/monitors/new")
async def new_monitor(request: Request, state: State, ctx: PageAuth) -> Response:
    defaults = MonitorConfig(name="", url="https://")
    return render(
        request, state, "monitor_form.html", ctx, form=defaults.__dict__, errors={}, monitor=None
    )


@router.post("/monitors/new")
async def create_monitor(request: Request, db: Db, state: State, ctx: PageAuth) -> Response:
    form = await _read_form(request)
    verify_form_csrf(ctx, form.get("csrf_token"))
    config, errors = _form_config(form)
    if config is not None:
        try:
            monitor = await monitor_service.create_monitor(
                db,
                config,
                now=state.clock.now(),
                policy=state.policy,
                min_interval_seconds=state.settings.min_interval_seconds,
                resolver=state.resolver,
            )
            await db.commit()
            return redirect(f"/monitors/{monitor.id}")
        except ValidationFailedError as exc:
            errors = exc.errors
    return render(
        request,
        state,
        "monitor_form.html",
        ctx,
        status_code=422,
        form=form,
        errors={e.field: e.message for e in errors},
        monitor=None,
    )


@router.get("/monitors/{monitor_id}")
async def monitor_detail(
    request: Request,
    monitor_id: int,
    db: Db,
    state: State,
    ctx: PageAuth,
    window: Annotated[str, Query(pattern="^(1h|24h|7d)$")] = "24h",
    outcome: Outcome | None = None,
    cursor: str | None = None,
) -> Response:
    try:
        monitor = await monitor_service.get_monitor(db, monitor_id)
    except NotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    now = state.clock.now()
    start = now - WINDOWS[window]
    worker = await queries.worker_status(
        db, now=now, stale_after=state.settings.worker_stale_after_seconds
    )
    try:
        checks = await queries.list_checks(
            db,
            monitor_id=monitor_id,
            limit=25,
            cursor=cursor,
            outcome=outcome.value if outcome else None,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    points = await queries.latency_series(db, monitor_id, start=start, end=now)
    incidents = await queries.list_incidents(db, monitor_id=monitor_id, limit=10)
    return render(
        request,
        state,
        "monitor_detail.html",
        ctx,
        monitor=monitor,
        stale=queries.is_stale(monitor, now=now, worker=worker),
        worker=worker,
        metrics=await queries.monitor_metrics(db, monitor_id, start=start, end=now, now=now),
        chart=build_latency_chart(points, monitor.latency_threshold_ms),
        changes=await queries.health_changes(db, monitor_id),
        checks=checks,
        incidents=[i for i, _m in incidents.items],
        window=window,
        outcome=outcome.value if outcome else "",
        outcomes=list(Outcome),
    )


@router.get("/monitors/{monitor_id}/edit")
async def edit_monitor_form(
    request: Request, monitor_id: int, db: Db, state: State, ctx: PageAuth
) -> Response:
    try:
        monitor = await monitor_service.get_monitor(db, monitor_id)
    except NotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    form = monitor_service.config_of(monitor).__dict__
    return render(request, state, "monitor_form.html", ctx, form=form, errors={}, monitor=monitor)


@router.post("/monitors/{monitor_id}/edit")
async def edit_monitor(
    request: Request, monitor_id: int, db: Db, state: State, ctx: PageAuth
) -> Response:
    form = await _read_form(request)
    verify_form_csrf(ctx, form.get("csrf_token"))
    config, errors = _form_config(form)
    if config is not None:
        try:
            await monitor_service.update_monitor(
                db,
                monitor_id,
                config,
                now=state.clock.now(),
                policy=state.policy,
                min_interval_seconds=state.settings.min_interval_seconds,
                resolver=state.resolver,
            )
            await db.commit()
            return redirect(f"/monitors/{monitor_id}")
        except NotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValidationFailedError as exc:
            errors = exc.errors
    monitor = await monitor_service.get_monitor(db, monitor_id)
    return render(
        request,
        state,
        "monitor_form.html",
        ctx,
        status_code=422,
        form=form,
        errors={e.field: e.message for e in errors},
        monitor=monitor,
    )


@router.post("/monitors/{monitor_id}/{action}")
async def monitor_action(
    monitor_id: int, action: str, db: Db, state: State, ctx: PageAuth, csrf_token: Csrf
) -> Response:
    verify_form_csrf(ctx, csrf_token)
    operations = {
        "pause": monitor_service.pause_monitor,
        "resume": monitor_service.resume_monitor,
        "archive": monitor_service.archive_monitor,
        "check": monitor_service.request_check_now,
    }
    if action not in operations:
        raise HTTPException(404, "ação desconhecida")
    try:
        await operations[action](db, monitor_id, now=state.clock.now())
    except NotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    await db.commit()
    return redirect(f"/monitors/{monitor_id}")


# ---- incidentes e notificações ------------------------------------------------------


@router.get("/incidents")
async def incidents_page(
    request: Request,
    db: Db,
    state: State,
    ctx: PageAuth,
    status: Annotated[str, Query(pattern="^(open|closed|all)$")] = "open",
    cursor: str | None = None,
) -> Response:
    try:
        page = await queries.list_incidents(
            db, status=None if status == "all" else status, limit=25, cursor=cursor
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return render(
        request, state, "incidents.html", ctx, page=page, status=status, now=state.clock.now()
    )


@router.get("/incidents/{incident_id}")
async def incident_page(
    request: Request, incident_id: int, db: Db, state: State, ctx: PageAuth
) -> Response:
    detail = await queries.incident_detail(db, incident_id)
    if detail is None:
        raise HTTPException(404, "incidente não encontrado")
    return render(request, state, "incident_detail.html", ctx, detail=detail, now=state.clock.now())


@router.get("/notifications")
async def notifications_page(request: Request, db: Db, state: State, ctx: PageAuth) -> Response:
    destinations = list(
        (await db.scalars(select(AlertDestination).order_by(AlertDestination.id))).all()
    )
    return render(
        request,
        state,
        "notifications.html",
        ctx,
        alerts=await queries.list_alerts(db, limit=50),
        destinations=destinations,
        errors={},
        form={},
    )


@router.post("/notifications/destinations")
async def create_destination(request: Request, db: Db, state: State, ctx: PageAuth) -> Response:
    form = await _read_form(request)
    verify_form_csrf(ctx, form.get("csrf_token"))
    name = form.get("name", "").strip()[:100]
    url = form.get("url", "").strip()[:2048]
    errors: dict[str, str] = {}
    if not name:
        errors["name"] = "obrigatório"
    try:
        await validate_destination(state.policy, url, state.resolver)
    except UnsafeDestinationError as exc:
        errors["url"] = str(exc)
    if not errors:
        now = state.clock.now()
        db.add(AlertDestination(name=name, url=url, enabled=True, created_at=now, updated_at=now))
        try:
            await db.commit()
            return redirect("/notifications")
        except IntegrityError:
            await db.rollback()
            errors["name"] = "já existe um destino com este nome"
    destinations = list(
        (await db.scalars(select(AlertDestination).order_by(AlertDestination.id))).all()
    )
    return render(
        request,
        state,
        "notifications.html",
        ctx,
        status_code=422,
        alerts=await queries.list_alerts(db, limit=50),
        destinations=destinations,
        errors=errors,
        form=form,
    )


@router.post("/notifications/destinations/{destination_id}/toggle")
async def toggle_destination(
    destination_id: int, db: Db, state: State, ctx: PageAuth, csrf_token: Csrf
) -> Response:
    verify_form_csrf(ctx, csrf_token)
    destination = await db.get(AlertDestination, destination_id)
    if destination is None:
        raise HTTPException(404, "destino não encontrado")
    destination.enabled = not destination.enabled
    destination.updated_at = state.clock.now()
    await db.commit()
    return redirect("/notifications")
