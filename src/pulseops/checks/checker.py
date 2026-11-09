"""Runs an HTTP check and classifies the result (RF02)."""

import asyncio
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import httpx

from pulseops.clock import Clock
from pulseops.domain.outcomes import Outcome
from pulseops.domain.status_codes import AcceptedStatusCodes
from pulseops.security.url_policy import UnsafeDestinationError


@dataclass(frozen=True)
class CheckTarget:
    url: str
    method: str
    timeout_seconds: float
    latency_threshold_ms: int
    accepted: AcceptedStatusCodes


@dataclass(frozen=True)
class CheckObservation:
    outcome: Outcome
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    status_code: int | None
    explanation: str


class Checker(Protocol):
    """Any object with this method works for the worker (useful for tests and new check types)."""

    async def check(self, target: CheckTarget) -> CheckObservation: ...


class HttpChecker:
    def __init__(self, client: httpx.AsyncClient, clock: Clock) -> None:
        self._client = client
        self._clock = clock

    async def check(self, target: CheckTarget) -> CheckObservation:
        started_at = self._clock.now()
        start = self._clock.monotonic()
        status_code: int | None = None
        try:
            # Total deadline for the check. HTTPX timeouts apply per phase (connect,
            # read...), so on their own they could add up to more than configured.
            async with asyncio.timeout(target.timeout_seconds):
                async with self._client.stream(
                    target.method,
                    target.url,
                    timeout=target.timeout_seconds,
                    follow_redirects=False,
                ) as response:
                    # The body is not read (RF02.4): the duration ends at the headers.
                    status_code = response.status_code
            outcome, explanation = self._classify_response(
                target, status_code, self._elapsed_ms(start)
            )
        except (TimeoutError, httpx.TimeoutException):
            outcome = Outcome.TIMEOUT
            explanation = f"no response in {target.timeout_seconds:g} s"
        except UnsafeDestinationError as exc:
            outcome = Outcome.BLOCKED
            explanation = f"destination blocked by the network policy: {exc}"
        except httpx.TransportError as exc:
            outcome, explanation = _classify_transport_error(exc)
        except Exception as exc:  # PulseOps' own error: it must not turn into "target is down"
            outcome = Outcome.INTERNAL_ERROR
            explanation = f"internal error while checking ({type(exc).__name__})"

        return CheckObservation(
            outcome=outcome,
            started_at=started_at,
            finished_at=self._clock.now(),
            duration_ms=self._elapsed_ms(start),
            status_code=status_code,
            explanation=explanation,
        )

    def _elapsed_ms(self, start: float) -> int:
        return round((self._clock.monotonic() - start) * 1000)

    @staticmethod
    def _classify_response(
        target: CheckTarget, status_code: int, duration_ms: int
    ) -> tuple[Outcome, str]:
        if status_code not in target.accepted:
            return (
                Outcome.UNEXPECTED_STATUS,
                f"HTTP {status_code} outside the accepted statuses ({target.accepted})",
            )
        if duration_ms > target.latency_threshold_ms:
            return (
                Outcome.SLOW,
                f"HTTP {status_code} in {duration_ms} ms (limit {target.latency_threshold_ms} ms)",
            )
        return Outcome.HEALTHY, f"HTTP {status_code} in {duration_ms} ms"


def _classify_transport_error(exc: httpx.TransportError) -> tuple[Outcome, str]:
    """Tells TLS apart from connection/DNS by walking the exception's cause chain."""
    causes = _cause_chain(exc)
    if any(isinstance(c, ssl.SSLCertVerificationError) for c in causes):
        return (
            Outcome.TLS_ERROR,
            "TLS failure: untrusted certificate or certificate for another name",
        )
    if any(isinstance(c, ssl.SSLError) for c in causes) or "SSL" in str(exc):
        return Outcome.TLS_ERROR, "TLS failure during the handshake"
    if isinstance(exc, httpx.ConnectError):
        if any(isinstance(c, socket.gaierror) for c in causes):
            return Outcome.CONNECTION_ERROR, "DNS failure: name not resolved"
        if any(isinstance(c, ConnectionRefusedError) for c in causes) or "refused" in str(exc):
            return Outcome.CONNECTION_ERROR, "connection refused"
        return Outcome.CONNECTION_ERROR, "connection failure"
    if isinstance(exc, httpx.RemoteProtocolError):
        return Outcome.CONNECTION_ERROR, "invalid HTTP response or connection closed by the target"
    return Outcome.CONNECTION_ERROR, f"network error ({type(exc).__name__})"


def _cause_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain
