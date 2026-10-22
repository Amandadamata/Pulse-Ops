"""Envio de eventos para um webhook genérico (RF06)."""

import asyncio
from typing import Any, Protocol

import httpx

from pulseops.clock import Clock
from pulseops.security.url_policy import DestinationPolicy, UnsafeDestinationError
from pulseops.services.alerts import SendResult, is_permanent_status


class Notifier(Protocol):
    async def send(self, url: str, event_id: str, payload: dict[str, Any]) -> SendResult: ...


class WebhookNotifier:
    def __init__(
        self,
        client: httpx.AsyncClient,
        clock: Clock,
        policy: DestinationPolicy,
        timeout_seconds: float,
    ) -> None:
        self._client = client
        self._clock = clock
        self._policy = policy
        self._timeout = timeout_seconds

    async def send(self, url: str, event_id: str, payload: dict[str, Any]) -> SendResult:
        start = self._clock.monotonic()

        def result(ok: bool, permanent: bool, status: int | None, error: str | None) -> SendResult:
            elapsed = round((self._clock.monotonic() - start) * 1000)
            return SendResult(ok, permanent, status, elapsed, error)

        try:
            self._policy.validate_url(url)  # a URL pode ter sido cadastrada com outra política
            async with asyncio.timeout(self._timeout):
                # stream(): só os cabeçalhos são lidos; o corpo da resposta é descartado.
                async with self._client.stream(
                    "POST",
                    url,
                    json=payload,
                    headers={"X-PulseOps-Event-Id": event_id},
                    timeout=self._timeout,
                ) as response:
                    status_code = response.status_code
        except UnsafeDestinationError as exc:
            return result(False, True, None, f"destino bloqueado: {exc}")
        except (TimeoutError, httpx.TimeoutException):
            return result(False, False, None, f"sem resposta em {self._timeout:g} s")
        except httpx.TransportError as exc:
            return result(False, False, None, f"erro de rede ({type(exc).__name__})")

        if 200 <= status_code < 300:
            return result(True, False, status_code, None)
        return result(False, is_permanent_status(status_code), status_code, f"HTTP {status_code}")
