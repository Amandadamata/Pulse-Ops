"""Worker: agenda verificações, entrega alertas e faz manutenção (ADR 0002).

Os três laços rodam no mesmo processo, mas em tarefas `asyncio` separadas. Assim
um webhook lento não atrasa nenhuma verificação (RF06.3).
"""

import asyncio
import contextlib
import logging
import os
import socket
from collections.abc import Awaitable, Callable
from datetime import timedelta

from sqlalchemy.dialects.postgresql import insert

from pulseops.checks.checker import Checker, CheckObservation
from pulseops.clock import Clock
from pulseops.config import Settings
from pulseops.db.models import WorkerHeartbeat
from pulseops.db.session import SessionFactory
from pulseops.domain.outcomes import Outcome
from pulseops.logs import log_context
from pulseops.notifications.webhook import Notifier
from pulseops.services import alerts, processing

logger = logging.getLogger(__name__)

DELIVERY_BATCH = 10
RETENTION_EVERY = timedelta(hours=1)


class Worker:
    def __init__(
        self,
        *,
        sessions: SessionFactory,
        checker: Checker,
        notifier: Notifier,
        clock: Clock,
        settings: Settings,
        worker_id: str | None = None,
    ) -> None:
        self._sessions = sessions
        self._checker = checker
        self._notifier = notifier
        self._clock = clock
        self._settings = settings
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self._started_at = clock.now()
        self._inflight: set[asyncio.Task[None]] = set()
        # Sinalizado sempre que um check termina e libera uma vaga (ver _wait_after_dispatch).
        self._slot_freed = asyncio.Event()
        self._last_retention = self._started_at - RETENTION_EVERY

    # ---- verificações -------------------------------------------------------------

    async def dispatch_checks(self) -> int:
        """Reserva execuções para as vagas livres e dispara cada uma em uma tarefa.

        O número de tarefas em andamento nunca passa de `worker_concurrency`: esse é o
        limite de concorrência das verificações.
        """
        claimed, _ = await self._dispatch()
        return claimed

    async def _dispatch(self) -> tuple[int, int]:
        """Devolve (reservadas, vagas pedidas)."""
        free = self._settings.worker_concurrency - len(self._inflight)
        runs = await processing.claim_due_runs(self._sessions, now=self._clock.now(), limit=free)
        for run in runs:
            task = asyncio.create_task(self._run_one(run), name=f"check:{run.run_key}")
            self._inflight.add(task)
            task.add_done_callback(self._release_slot)
        return len(runs), free

    def _release_slot(self, task: asyncio.Task[None]) -> None:
        self._inflight.discard(task)
        self._slot_freed.set()

    async def _wait_after_dispatch(self, claimed: int, requested: int) -> None:
        """Se todas as vagas pedidas foram preenchidas, pode haver fila: volta assim que
        uma vaga abrir, em vez de dormir o tick inteiro (bug B8). Se vieram menos
        execuções que vagas, nada mais está vencido e o tick normal basta."""
        tick = self._settings.worker_tick_seconds
        if claimed < requested:
            await asyncio.sleep(tick)
            return
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._slot_freed.wait(), timeout=tick)

    async def wait_inflight(self) -> None:
        if self._inflight:
            await asyncio.gather(*self._inflight, return_exceptions=True)

    async def run_checks_once(self) -> int:
        """Usado pelos testes: reserva, executa e grava tudo que estiver vencido agora."""
        count = await self.dispatch_checks()
        await self.wait_inflight()
        return count

    async def _run_one(self, run: processing.ClaimedRun) -> None:
        with log_context(monitor_id=run.monitor_id, run_key=run.run_key):
            try:
                observation = await self._checker.check(run.target)
            except Exception as exc:  # o verificador já trata erros; isto é a última barreira
                logger.exception("erro inesperado no verificador")
                now = self._clock.now()
                observation = CheckObservation(
                    Outcome.INTERNAL_ERROR,
                    now,
                    now,
                    0,
                    None,
                    f"erro interno ({type(exc).__name__})",
                )
            try:
                await processing.record_result(self._sessions, run, observation)
            except Exception:
                # Banco fora do ar, por exemplo. O check fica 'running' e a manutenção o marca
                # como interrompido depois; nada é contado como falha do alvo.
                logger.exception("falha ao gravar resultado do check")

    # ---- alertas ------------------------------------------------------------------

    async def run_deliveries_once(self) -> int:
        s = self._settings
        claimed = await alerts.claim_due_deliveries(
            self._sessions,
            now=self._clock.now(),
            limit=DELIVERY_BATCH,
            lease_seconds=s.webhook_timeout_seconds + 30,
        )
        await asyncio.gather(*(self._deliver(item) for item in claimed))
        return len(claimed)

    async def _deliver(self, item: alerts.ClaimedDelivery) -> None:
        s = self._settings
        with log_context(delivery_id=item.delivery_id, event_id=item.event_key):
            result = await self._notifier.send(item.url, item.event_key, item.payload)
            try:
                status = await alerts.record_delivery_result(
                    self._sessions,
                    item,
                    result,
                    now=self._clock.now(),
                    max_attempts=s.webhook_max_attempts,
                    backoff_base=s.webhook_backoff_base_seconds,
                    backoff_max=s.webhook_backoff_max_seconds,
                )
            except Exception:
                logger.exception("falha ao gravar tentativa de entrega")
                return
            level = logging.INFO if result.ok else logging.WARNING
            logger.log(
                level,
                "tentativa de entrega",
                extra={"attempt": item.attempt_number, "status": status, "error": result.error},
            )

    # ---- manutenção ---------------------------------------------------------------

    async def heartbeat(self) -> None:
        now = self._clock.now()
        statement = insert(WorkerHeartbeat).values(
            worker_id=self.worker_id,
            hostname=socket.gethostname(),
            pid=os.getpid(),
            started_at=self._started_at,
            last_seen_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=["worker_id"], set_={"last_seen_at": now}
        )
        async with self._sessions.begin() as session:
            await session.execute(statement)

    async def run_maintenance_once(self) -> None:
        await self.heartbeat()
        now = self._clock.now()
        await processing.mark_abandoned_runs(self._sessions, now=now)
        if now - self._last_retention >= RETENTION_EVERY:
            removed = await processing.purge_old_checks(
                self._sessions, now=now, retention_days=self._settings.check_retention_days
            )
            self._last_retention = now
            if removed:
                logger.info("retenção: checks antigos removidos", extra={"count": removed})

    # ---- laço principal -----------------------------------------------------------

    async def run(self, stop: asyncio.Event) -> None:
        s = self._settings
        logger.info("worker iniciado", extra={"worker_id": self.worker_id})
        loops = [
            self._check_loop(stop),
            self._loop("deliveries", self.run_deliveries_once, s.worker_tick_seconds, stop),
            self._loop(
                "maintenance", self.run_maintenance_once, s.heartbeat_interval_seconds, stop
            ),
        ]
        await asyncio.gather(*loops)
        logger.info("aguardando checks em andamento terminarem")
        await self.wait_inflight()

    async def _check_loop(self, stop: asyncio.Event) -> None:
        failures = 0
        while not stop.is_set():
            self._slot_freed.clear()
            try:
                claimed, requested = await self._dispatch()
                failures = 0
            except Exception:
                failures += 1
                delay = min(self._settings.worker_tick_seconds * 2**failures, 30.0)
                logger.exception(
                    "erro no laço do worker", extra={"loop": "checks", "retry_in": delay}
                )
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=delay)
                continue
            waiter = asyncio.create_task(self._wait_after_dispatch(claimed, requested))
            stopper = asyncio.create_task(stop.wait())
            await asyncio.wait({waiter, stopper}, return_when=asyncio.FIRST_COMPLETED)
            waiter.cancel()
            stopper.cancel()

    async def _loop(
        self, name: str, step: Callable[[], Awaitable[object]], every: float, stop: asyncio.Event
    ) -> None:
        failures = 0
        while not stop.is_set():
            try:
                await step()
                failures = 0
                delay = every
            except Exception:
                # Banco indisponível, por exemplo: registra e tenta de novo com espera crescente,
                # sem derrubar o processo e sem afetar os outros laços.
                failures += 1
                delay = min(every * 2**failures, 30.0)
                logger.exception("erro no laço do worker", extra={"loop": name, "retry_in": delay})
            # Espera o intervalo, mas acorda na hora se o processo receber sinal de parada.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=delay)
