"""Controllable lab target.

GET /service answers according to the current mode:
- healthy: 200 right away
- slow: 200 after SLOW_SECONDS (above the demo latency limit)
- error: 500
- timeout: waits TIMEOUT_SECONDS (longer than the demo timeout)

GET /stable always answers 200 (the second demo monitor, which never fails).

POST /control/mode {"mode": "..."} changes the mode. It only exists inside the Compose network.
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
        return PlainTextResponse("simulated error", status_code=500)
    return PlainTextResponse("ok")


@app.api_route("/stable", methods=["GET", "HEAD"])
async def stable() -> PlainTextResponse:
    return PlainTextResponse("ok")


@app.post("/control/mode")
async def set_mode(body: ModeIn) -> dict[str, str]:
    app.state.mode = body.mode
    return {"mode": body.mode}


@app.get("/control/state")
async def get_state() -> dict[str, object]:
    return {"mode": app.state.mode, "requests": app.state.requests}
