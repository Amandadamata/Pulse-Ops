"""Worker: schedules checks, delivers alerts and does maintenance (ADR 0002).

The three loops run in the same process, but in separate `asyncio` tasks. This way
a slow webhook never delays a check (RF06.3).
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
        # Signaled whenever a check finishes and frees a slot (see _wait_after_dispatch).
        self._slot_freed = asyncio.Event()
        self._last_retention = self._started_at - RETENTION_EVERY

    # ---- checks --------------------------------------------------------------------

    async def dispatch_checks(self) -> int:
        """Reserves runs for the free slots and starts each one in a task.

        The number of running tasks never exceeds `worker_concurrency`: that is the
        concurrency limit for checks.
        """
        claimed, _ = await self._dispatch()
        return claimed

    async def _dispatch(self) -> tuple[int, int]:
        """Returns (reserved, slots requested)."""
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
        """If every requested slot was filled, there may be a queue: come back as soon as
        a slot opens, instead of sleeping the whole tick (bug B8). If fewer runs came
        back than slots, nothing else is due and the normal tick is enough."""
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
        """Used by the tests: reserves, runs and saves everything that is due right now."""
        count = await self.dispatch_checks()
        await self.wait_inflight()
        return count

    async def _run_one(self, run: processing.ClaimedRun) -> None:
        with log_context(monitor_id=run.monitor_id, run_key=run.run_key):
            try:
                observation = await self._checker.check(run.target)
            except (
                Exception
            ) as exc:  # the checker already handles errors; this is the last safety net
                logger.exception("unexpected error in the checker")
                now = self._clock.now()
                observation = CheckObservation(
                    Outcome.INTERNAL_ERROR,
                    now,
                    now,
                    0,
                    None,
                    f"internal error ({type(exc).__name__})",
                )
            try:
                await processing.record_result(self._sessions, run, observation)
            except Exception:
                # The database is down, for example. The check stays 'running' and maintenance marks
                # it as interrupted later; nothing counts as a target failure.
                logger.exception("failed to save the check result")

    # ---- alerts -------------------------------------------------------------------

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
                logger.exception("failed to save the delivery attempt")
                return
            level = logging.INFO if result.ok else logging.WARNING
            logger.log(
                level,
                "delivery attempt",
                extra={"attempt": item.attempt_number, "status": status, "error": result.error},
            )

    # ---- maintenance ---------------------------------------------------------------

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
                logger.info("retention: old checks removed", extra={"count": removed})

    # ---- main loop -----------------------------------------------------------------

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
        logger.info("waiting for checks in progress to finish")
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
                    "error in the worker loop", extra={"loop": "checks", "retry_in": delay}
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
                # The database is down, for example: log it and try again with a growing wait,
                # without bringing down the process and without affecting the other loops.
                failures += 1
                delay = min(every * 2**failures, 30.0)
                logger.exception(
                    "error in the worker loop", extra={"loop": name, "retry_in": delay}
                )
            # Waits for the interval, but wakes up right away if the process receives a stop signal.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=delay)
