"""Failure lab script (run by the demo-runner service).

Each step prints what it is checking and exits with code 1 if the check is not
confirmed in time. It can run several times: monitors and the destination are
looked up by name before they are created.

Variables: PULSEOPS_DEMO_API, PULSEOPS_DEMO_TARGET, PULSEOPS_DEMO_RECEIVER,
PULSEOPS_DEMO_USERNAME and PULSEOPS_DEMO_PASSWORD.
"""

import os
import re
import sys
import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx

T = TypeVar("T")
TOTAL_STEPS = 11
CSRF_FIELD = re.compile(r'name="csrf_token" value="([^"]+)"')

MAIN: dict[str, Any] = {
    "name": "Lab: main service",
    "description": "Target controlled by the demo script.",
    "url": "http://lab-target:8081/service",
    "method": "GET",
    "interval_seconds": 3,
    "timeout_seconds": 2,
    "accepted_status_codes": "200-299",
    "latency_threshold_ms": 800,
    "failure_threshold": 3,
    "recovery_threshold": 2,
}
STABLE: dict[str, Any] = {
    **MAIN,
    "name": "Lab: stable service",
    "description": "Always answers 200; used for comparison on the dashboard.",
    "url": "http://lab-target:8081/stable",
    "interval_seconds": 5,
}
DESTINATION = {"name": "Lab receiver", "url": "http://lab-receiver:8082/webhook"}


class StepFailedError(Exception):
    pass


class Demo:
    def __init__(self, api: str, target: str, receiver: str) -> None:
        self.api = httpx.Client(base_url=api, timeout=10)
        self.target = httpx.Client(base_url=target, timeout=10)
        self.receiver = httpx.Client(base_url=receiver, timeout=10)
        self.csrf = ""

    # ---- output and checks -----------------------------------------------------------

    @staticmethod
    def step(number: int, title: str) -> None:
        print(f"\n[{number}/{TOTAL_STEPS}] {title}", flush=True)

    @staticmethod
    def ok(message: str) -> None:
        print(f"    ok: {message}", flush=True)

    def expect(self, condition: bool, message: str) -> None:
        if not condition:
            raise StepFailedError(message)
        self.ok(message)

    @staticmethod
    def wait_for(description: str, probe: Callable[[], T | None], timeout: float) -> T:
        print(f"    waiting for: {description} (up to {timeout:.0f} s)", flush=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = probe()
            if value:
                return value
            time.sleep(0.5)
        raise StepFailedError(f"tempo esgotado esperando: {description}")

    # ---- PulseOps API ---------------------------------------------------------------

    def login(self, username: str, password: str) -> None:
        page = self.api.get("/login")
        token = CSRF_FIELD.search(page.text)
        if not token:
            raise StepFailedError("login page without a CSRF token")
        response = self.api.post(
            "/login",
            data={"username": username, "password": password, "csrf_token": token.group(1)},
        )
        if response.status_code != 303:
            raise StepFailedError(f"login recusado (HTTP {response.status_code})")
        token = CSRF_FIELD.search(self.api.get("/").text)
        if not token:
            raise StepFailedError("dashboard without a CSRF token after login")
        self.csrf = token.group(1)

    def get(self, path: str, **params: Any) -> Any:
        response = self.api.get(f"/api/v1{path}", params=params)
        response.raise_for_status()
        return response.json()

    def send(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        response = self.api.request(
            method, f"/api/v1{path}", json=body, headers={"X-CSRF-Token": self.csrf}
        )
        if response.status_code >= 400:
            raise StepFailedError(f"{method} {path}: HTTP {response.status_code} {response.text}")
        return response.json()

    def monitors_named(self, name: str) -> list[dict[str, Any]]:
        monitors: list[dict[str, Any]] = self.get("/monitors")
        return [m for m in monitors if m["name"].lower() == name.lower()]

    def ensure_monitor(self, spec: dict[str, Any], *, reset: bool) -> dict[str, Any]:
        found = self.monitors_named(spec["name"])
        if not found:
            created: dict[str, Any] = self.send("POST", "/monitors", spec)
            self.ok(f"monitor created: {spec['name']} (id {created['id']})")
            return created
        monitor = found[0]
        self.send("PUT", f"/monitors/{monitor['id']}", spec)
        if monitor["state"] == "active" and reset:
            # Pausing closes an incident left over from a previous run and resets the
            # counters; resuming schedules the first check right away.
            self.send("POST", f"/monitors/{monitor['id']}/pause")
        if monitor["state"] == "paused" or reset:
            self.send("POST", f"/monitors/{monitor['id']}/resume")
        self.ok(f"monitor already existed and was reused: {spec['name']} (id {monitor['id']})")
        refreshed: dict[str, Any] = self.get(f"/monitors/{monitor['id']}")
        return refreshed

    def ensure_destination(self) -> None:
        destinations: list[dict[str, Any]] = self.get("/destinations")
        for d in destinations:
            if d["name"] == DESTINATION["name"]:
                if not d["enabled"]:
                    self.send("PATCH", f"/destinations/{d['id']}", {"enabled": True})
                self.ok(f"alert destination already existed: {d['name']}")
                return
        self.send("POST", "/destinations", {**DESTINATION, "enabled": True})
        self.ok(f"alert destination created: {DESTINATION['name']}")

    def checks_after(self, monitor_id: int, after_id: int) -> list[dict[str, Any]]:
        """Finished checks with id greater than `after_id`, oldest first."""
        page = self.get(f"/monitors/{monitor_id}/checks", limit=100)
        items = [c for c in page["items"] if c["id"] > after_id and c["outcome"] is not None]
        return sorted(items, key=lambda c: c["id"])

    def last_check_id(self, monitor_id: int) -> int:
        page = self.get(f"/monitors/{monitor_id}/checks", limit=1)
        return int(page["items"][0]["id"]) if page["items"] else 0

    def open_incidents(self, monitor_id: int) -> list[dict[str, Any]]:
        page = self.get("/incidents", status="open", monitor_id=monitor_id)
        items: list[dict[str, Any]] = page["items"]
        return items

    def settled_delivery(self, incident_id: int, event_id: str) -> dict[str, Any] | None:
        """The event delivery, if an attempt was made and the worker saved the result.

        The worker reserves the delivery (status 'sending', attempt_count + 1) before sending and
        only saves the result afterwards. In between, the attempt has no outcome yet.
        """
        for alert in self.get(f"/incidents/{incident_id}")["alerts"]:
            for delivery in alert["deliveries"]:
                if (
                    alert["event_id"] == event_id
                    and delivery["attempt_count"] >= 1
                    and delivery["status"] != "sending"
                ):
                    return dict(delivery)
        return None

    # ---- lab -------------------------------------------------------------------------

    def set_target(self, mode: str) -> None:
        self.target.post("/control/mode", json={"mode": mode}).raise_for_status()
        self.ok(f"lab target now in '{mode}' mode")

    def set_receiver(self, available: bool) -> None:
        self.receiver.post(
            "/control/availability", json={"available": available}
        ).raise_for_status()
        self.ok(f"alert receiver {'available' if available else 'unavailable (503)'}")

    def received(self) -> dict[str, Any]:
        data: dict[str, Any] = self.receiver.get("/control/received").json()
        return data


def run(demo: Demo, username: str, password: str) -> None:
    demo.step(1, "Environment up: API ready, database reachable and worker running")
    ready = demo.api.get("/health/ready")
    demo.expect(ready.status_code == 200, f"/health/ready respondeu {ready.status_code}")
    demo.login(username, password)
    demo.ok(f"logged in as '{username}'")
    demo.wait_for("worker sending a heartbeat", lambda: demo.get("/summary")["worker_alive"], 30)
    demo.ok("worker active according to /api/v1/summary")

    demo.step(2, "Prepare monitors without duplicates (idempotent)")
    demo.set_target("healthy")
    demo.set_receiver(True)
    demo.ensure_destination()
    main = demo.ensure_monitor(MAIN, reset=True)
    demo.ensure_monitor(STABLE, reset=False)
    for spec in (MAIN, STABLE):
        count = len(demo.monitors_named(spec["name"]))
        demo.expect(count == 1, f"there is exactly 1 monitor '{spec['name']}' (found {count})")
    mid = main["id"]
    baseline = demo.last_check_id(mid)

    demo.step(3, "Healthy checks")
    demo.wait_for(
        "2 successful checks and 'healthy' status",
        lambda: (
            sum(c["outcome"] == "healthy" for c in demo.checks_after(mid, baseline)) >= 2
            and demo.get(f"/monitors/{mid}")["health"] == "healthy"
        ),
        30,
    )
    demo.ok(f"reason shown: {demo.get(f'/monitors/{mid}')['health_reason']}")
    demo.set_target("slow")
    mark = demo.last_check_id(mid)
    slow = demo.wait_for(
        "one slow check (above 800 ms, below the 2 s timeout)",
        lambda: [c for c in demo.checks_after(mid, mark) if c["outcome"] == "slow"],
        20,
    )
    monitor = demo.get(f"/monitors/{mid}")
    demo.expect(
        monitor["health"] == "degraded" and not demo.open_incidents(mid),
        f"slowness ({slow[0]['duration_ms']} ms) leaves the monitor degraded, no incident",
    )

    demo.step(4, "Cause a failure (timeout)")
    demo.set_target("timeout")
    mark = demo.last_check_id(mid)
    demo.wait_for(
        "one check with a 'timeout' result",
        lambda: [c for c in demo.checks_after(mid, mark) if c["outcome"] == "timeout"],
        20,
    )
    monitor = demo.get(f"/monitors/{mid}")
    demo.expect(not demo.open_incidents(mid), "a single failure does not open an incident yet")
    demo.ok(f"reason shown: {monitor['health_reason']}")

    demo.step(5, "Opening threshold: 3 consecutive failures confirm the incident")
    demo.set_target("error")
    incident = demo.wait_for("open incident", lambda: demo.open_incidents(mid), 40)[0]
    demo.expect(
        incident["opening_reason"].startswith("Incident confirmed after 3 consecutive failures"),
        f"opening reason: {incident['opening_reason']}",
    )
    detail = demo.get(f"/incidents/{incident['id']}")
    kinds = [e["kind"] for e in detail["events"]]
    demo.expect(
        kinds[:2] == ["first_failure", "opened"],
        f"timeline starts with the first failure and the confirmation: {kinds}",
    )
    demo.wait_for(
        "incident.opened alert reaching the receiver",
        lambda: f"incident:{incident['id']}:opened" in demo.received()["event_ids"],
        20,
    )
    demo.ok("receiver got incident.opened")

    demo.step(6, "Further failures do not open another incident")
    mark = demo.last_check_id(mid)
    demo.wait_for(
        "2 more failed checks",
        lambda: sum(c["outcome"] == "unexpected_status" for c in demo.checks_after(mid, mark)) >= 2,
        20,
    )
    still_open = demo.open_incidents(mid)
    demo.expect(
        len(still_open) == 1 and still_open[0]["id"] == incident["id"],
        f"there is only ONE open incident (id {incident['id']})",
    )

    demo.step(7, "Restore the target")
    demo.set_target("healthy")
    mark = demo.last_check_id(mid)
    demo.wait_for(
        "1 successful check",
        lambda: [c for c in demo.checks_after(mid, mark) if c["outcome"] == "healthy"],
        20,
    )
    monitor = demo.get(f"/monitors/{mid}")
    if demo.open_incidents(mid):
        demo.ok(f"one success does not close it yet: {monitor['health_reason']}")

    demo.step(8, "Recovery: 2 consecutive successes close the incident")
    demo.wait_for("incident resolved", lambda: not demo.open_incidents(mid), 20)
    resolved = demo.get(f"/incidents/{incident['id']}")["incident"]
    demo.expect(resolved["status"] == "resolved", f"reason: {resolved['resolution_explanation']}")
    demo.expect(demo.get(f"/monitors/{mid}")["health"] == "healthy", "monitor back to 'healthy'")
    demo.wait_for(
        "incident.resolved alert reaching the receiver",
        lambda: f"incident:{incident['id']}:resolved" in demo.received()["event_ids"],
        20,
    )
    demo.ok("receiver got incident.resolved")

    demo.step(9, "Take the alert receiver down and cause a new incident")
    demo.set_receiver(False)
    rejected_before = demo.received()["rejected"]
    demo.set_target("error")
    second = demo.wait_for("new open incident", lambda: demo.open_incidents(mid), 40)[0]
    event_id = f"incident:{second['id']}:opened"

    delivery = demo.wait_for(
        "delivery attempt refused by the receiver",
        lambda: demo.settled_delivery(second["id"], event_id),
        20,
    )
    demo.expect(
        delivery["status"] == "pending" and "503" in (delivery["last_error"] or ""),
        f"delivery status: {delivery['status']}, last error: {delivery['last_error']}",
    )
    demo.expect(demo.received()["rejected"] > rejected_before, "receiver recorded the refusal")

    demo.step(10, "Monitoring continues while the receiver is down")
    mark = demo.last_check_id(mid)
    demo.wait_for("2 more checks saved", lambda: len(demo.checks_after(mid, mark)) >= 2, 20)
    demo.expect(
        event_id not in demo.received()["event_ids"],
        "checks keep being saved while the alert waits",
    )

    demo.step(11, "Bring the receiver back and watch the retry deliver the alert")
    demo.set_receiver(True)
    demo.wait_for(
        "alert reaching the receiver",
        lambda: event_id in demo.received()["event_ids"],
        30,
    )
    final = demo.wait_for(
        "worker saving the finished delivery",
        lambda: demo.settled_delivery(second["id"], event_id),
        20,
    )
    demo.expect(
        final["status"] == "delivered" and final["attempt_count"] >= 2,
        f"delivered on attempt {final['attempt_count']}",
    )
    # "At least once" delivery: if the same event arrives again, the receiver
    # recognizes it by id and does not process it twice.
    payload = demo.received()
    repost = demo.receiver.post(
        "/webhook", json={"type": "incident.opened"}, headers={"X-PulseOps-Event-Id": event_id}
    ).json()
    after = demo.received()
    demo.expect(
        repost["duplicate"] and after["duplicates"] == payload["duplicates"] + 1,
        "resending the same event was recognized as a duplicate",
    )
    demo.set_target("healthy")
    print("\nDemo finished: all 11 steps were verified.", flush=True)


def main() -> int:
    password = os.environ.get("PULSEOPS_DEMO_PASSWORD", "")
    if not password:
        print("error: set PULSEOPS_DEMO_PASSWORD (scripts/demo.sh does that)", file=sys.stderr)
        return 2
    demo = Demo(
        os.environ.get("PULSEOPS_DEMO_API", "http://api:8000"),
        os.environ.get("PULSEOPS_DEMO_TARGET", "http://lab-target:8081"),
        os.environ.get("PULSEOPS_DEMO_RECEIVER", "http://lab-receiver:8082"),
    )
    try:
        run(demo, os.environ.get("PULSEOPS_DEMO_USERNAME", "demo"), password)
    except (StepFailedError, httpx.HTTPError) as exc:
        print(f"\nFALHOU: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
