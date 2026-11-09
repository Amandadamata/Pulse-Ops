"""Lab script: reading the delivery while the worker is still sending (B11)."""

from typing import Any

import httpx
import pytest

from scripts import demo_flow
from scripts.demo_flow import Demo

EVENT_ID = "incident:2:opened"
NOT_ATTEMPTED = {"status": "pending", "attempt_count": 0, "last_error": None}
BEING_SENT = {"status": "sending", "attempt_count": 1, "last_error": None}
REFUSED = {"status": "pending", "attempt_count": 1, "last_error": "HTTP 503"}
RETRYING = {"status": "sending", "attempt_count": 2, "last_error": "HTTP 503"}
DELIVERED = {"status": "delivered", "attempt_count": 2, "last_error": None}


def demo_reading(*deliveries: dict[str, Any]) -> Demo:
    """Demo whose API returns, on each incident read, the next delivery state."""
    states = iter(deliveries)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/incidents/2"
        alert = {"event_id": EVENT_ID, "deliveries": [next(states)]}
        other = {"event_id": "incident:1:opened", "deliveries": [REFUSED]}
        return httpx.Response(200, json={"alerts": [other, alert]})

    demo = Demo("http://api", "http://target", "http://receiver")
    demo.api = httpx.Client(base_url="http://api", transport=httpx.MockTransport(handler))
    return demo


@pytest.mark.parametrize("state", [NOT_ATTEMPTED, BEING_SENT, RETRYING])
def test_attempt_without_recorded_result_is_not_settled(state: dict[str, Any]) -> None:
    assert demo_reading(state).settled_delivery(2, EVENT_ID) is None


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        ((BEING_SENT, REFUSED), REFUSED),  # step 9: the race that broke CI
        (
            (RETRYING, DELIVERED),
            DELIVERED,
        ),  # step 11: the receiver already got it, the worker has not saved it
    ],
)
def test_waits_for_the_worker_to_record_the_attempt(
    monkeypatch: pytest.MonkeyPatch,
    states: tuple[dict[str, Any], ...],
    expected: dict[str, Any],
) -> None:
    monkeypatch.setattr(demo_flow.time, "sleep", lambda _seconds: None)
    demo = demo_reading(*states)
    settled = Demo.wait_for("resultado", lambda: demo.settled_delivery(2, EVENT_ID), 5)
    assert settled == expected
