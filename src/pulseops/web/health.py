"""Liveness e readiness do próprio PulseOps (RF09). Não exigem login."""

import asyncio
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from pulseops.services import queries
from pulseops.web.deps import State

router = APIRouter(prefix="/health", tags=["health"])

READY_TIMEOUT_SECONDS = 2.0


@router.get("/live")
async def live() -> dict[str, str]:
    """O processo está respondendo. Não consulta o banco de propósito."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(state: State) -> JSONResponse:
    """Pronto para atender: o banco responde em até 2 s. O worker é informado, mas a API
    continua pronta sem ele (o painel mostra os dados como desatualizados)."""
    body: dict[str, Any] = {"status": "ok", "database": "ok"}
    try:
        async with asyncio.timeout(READY_TIMEOUT_SECONDS):
            async with state.sessions() as session:
                await session.execute(text("SELECT 1"))
                worker = await queries.worker_status(
                    session,
                    now=state.clock.now(),
                    stale_after=state.settings.worker_stale_after_seconds,
                )
    except Exception:
        body.update(status="unavailable", database="unavailable")
        return JSONResponse(body, status_code=503)
    body["worker"] = {
        "alive": worker.alive,
        "last_seen_at": worker.last_seen_at.isoformat() if worker.last_seen_at else None,
    }
    return JSONResponse(body)
