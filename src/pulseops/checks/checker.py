"""Executa uma verificação HTTP e classifica o resultado (RF02)."""

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
    """Qualquer objeto com este método serve ao worker (útil para testes e novos tipos)."""

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
            # Prazo total da verificação. Os timeouts do HTTPX valem por fase (conectar,
            # ler...), então sozinhos poderiam somar mais que o configurado.
            async with asyncio.timeout(target.timeout_seconds):
                async with self._client.stream(
                    target.method,
                    target.url,
                    timeout=target.timeout_seconds,
                    follow_redirects=False,
                ) as response:
                    # O corpo não é lido (RF02.4): a duração vai até os cabeçalhos.
                    status_code = response.status_code
            outcome, explanation = self._classify_response(
                target, status_code, self._elapsed_ms(start)
            )
        except (TimeoutError, httpx.TimeoutException):
            outcome = Outcome.TIMEOUT
            explanation = f"sem resposta em {target.timeout_seconds:g} s"
        except UnsafeDestinationError as exc:
            outcome = Outcome.BLOCKED
            explanation = f"destino bloqueado pela política de rede: {exc}"
        except httpx.TransportError as exc:
            outcome, explanation = _classify_transport_error(exc)
        except Exception as exc:  # erro do próprio PulseOps: não pode virar "alvo caiu"
            outcome = Outcome.INTERNAL_ERROR
            explanation = f"erro interno ao verificar ({type(exc).__name__})"

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
                f"HTTP {status_code} fora dos status aceitos ({target.accepted})",
            )
        if duration_ms > target.latency_threshold_ms:
            return (
                Outcome.SLOW,
                f"HTTP {status_code} em {duration_ms} ms (limite {target.latency_threshold_ms} ms)",
            )
        return Outcome.HEALTHY, f"HTTP {status_code} em {duration_ms} ms"


def _classify_transport_error(exc: httpx.TransportError) -> tuple[Outcome, str]:
    """Separa TLS de conexão/DNS olhando a cadeia de causas da exceção."""
    causes = _cause_chain(exc)
    if any(isinstance(c, ssl.SSLCertVerificationError) for c in causes):
        return Outcome.TLS_ERROR, "falha TLS: certificado não confiável ou de outro nome"
    if any(isinstance(c, ssl.SSLError) for c in causes) or "SSL" in str(exc):
        return Outcome.TLS_ERROR, "falha TLS durante o handshake"
    if isinstance(exc, httpx.ConnectError):
        if any(isinstance(c, socket.gaierror) for c in causes):
            return Outcome.CONNECTION_ERROR, "falha de DNS: nome não resolvido"
        if any(isinstance(c, ConnectionRefusedError) for c in causes) or "refused" in str(exc):
            return Outcome.CONNECTION_ERROR, "conexão recusada"
        return Outcome.CONNECTION_ERROR, "falha de conexão"
    if isinstance(exc, httpx.RemoteProtocolError):
        return Outcome.CONNECTION_ERROR, "resposta HTTP inválida ou conexão encerrada pelo alvo"
    return Outcome.CONNECTION_ERROR, f"erro de rede ({type(exc).__name__})"


def _cause_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain
