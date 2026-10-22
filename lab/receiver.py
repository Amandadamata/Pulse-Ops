"""Receptor de webhooks do laboratório, com deduplicação por X-PulseOps-Event-Id.

POST /webhook: se `available` for falso, responde 503 (simula destino fora do ar).
Eventos repetidos (mesmo id) são aceitos com 200 mas contados como duplicados,
que é o que um receptor real deve fazer com entrega "pelo menos uma vez".
"""

from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="PulseOps lab receiver", docs_url=None, redoc_url=None, openapi_url=None)


class Inbox:
    def __init__(self) -> None:
        self.available = True
        self.events: dict[str, dict[str, Any]] = {}
        self.order: list[str] = []
        self.duplicates = 0
        self.rejected = 0

    def receive(self, event_id: str, payload: dict[str, Any]) -> bool:
        """Guarda o evento. Devolve False se o id já tinha sido recebido."""
        if event_id in self.events:
            self.duplicates += 1
            return False
        self.events[event_id] = payload
        self.order.append(event_id)
        return True


inbox = Inbox()


class AvailabilityIn(BaseModel):
    available: bool


@app.post("/webhook")
async def webhook(
    request: Request, x_pulseops_event_id: str | None = Header(default=None)
) -> JSONResponse:
    if not inbox.available:
        inbox.rejected += 1
        return JSONResponse({"detail": "receptor indisponível (simulado)"}, status_code=503)
    if not x_pulseops_event_id:
        return JSONResponse({"detail": "X-PulseOps-Event-Id ausente"}, status_code=400)
    payload = await request.json()
    new = inbox.receive(x_pulseops_event_id, payload)
    return JSONResponse({"duplicate": not new})


@app.post("/control/availability")
async def set_availability(body: AvailabilityIn) -> dict[str, bool]:
    inbox.available = body.available
    return {"available": inbox.available}


@app.get("/control/received")
async def received() -> dict[str, Any]:
    return {
        "available": inbox.available,
        "event_ids": inbox.order,
        "types": [inbox.events[i].get("type") for i in inbox.order],
        "duplicates": inbox.duplicates,
        "rejected": inbox.rejected,
    }
