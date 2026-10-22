"""Alvo controlável do laboratório.

GET /service responde conforme o modo atual:
- healthy: 200 imediato
- slow: 200 depois de SLOW_SECONDS (acima do limite de latência da demo)
- error: 500
- timeout: espera TIMEOUT_SECONDS (mais que o timeout da demo)

POST /control/mode {"mode": "..."} troca o modo. Só existe dentro da rede do Compose.
"""

import asyncio
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

Mode = Literal["healthy", "slow", "error", "timeout"]
SLOW_SECONDS = 1.5
TIMEOUT_SECONDS = 30.0

app = FastAPI(title="PulseOps lab target", docs_url=None, redoc_url=None, openapi_url=None)
app.state.mode = "healthy"
app.state.requests = 0


class ModeIn(BaseModel):
    mode: Mode


@app.api_route("/service", methods=["GET", "HEAD"])
async def service() -> PlainTextResponse:
    app.state.requests += 1
    mode = app.state.mode
    if mode == "slow":
        await asyncio.sleep(SLOW_SECONDS)
    elif mode == "timeout":
        await asyncio.sleep(TIMEOUT_SECONDS)
    elif mode == "error":
        return PlainTextResponse("erro simulado", status_code=500)
    return PlainTextResponse("ok")


@app.post("/control/mode")
async def set_mode(body: ModeIn) -> dict[str, str]:
    app.state.mode = body.mode
    return {"mode": body.mode}


@app.get("/control/state")
async def get_state() -> dict[str, object]:
    return {"mode": app.state.mode, "requests": app.state.requests}
