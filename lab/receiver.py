"""Lab webhook receiver, with deduplication by X-PulseOps-Event-Id.

POST /webhook: if `available` is false, it answers 503 (simulates a destination that is down).
Repeated events (same id) are accepted with 200 but counted as duplicates,
which is what a real receiver should do with "at least once" delivery.
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
        """Stores the event. Returns False if the id had already been received."""
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
        return JSONResponse({"detail": "receiver unavailable (simulated)"}, status_code=503)
    if not x_pulseops_event_id:
        return JSONResponse({"detail": "missing X-PulseOps-Event-Id"}, status_code=400)
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
