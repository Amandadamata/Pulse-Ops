"""Ponto de entrada: `python -m pulseops.worker`."""

import asyncio
import logging
import signal
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from pulseops import __version__
from pulseops.checks.checker import HttpChecker
from pulseops.clock import SystemClock
from pulseops.config import Settings
from pulseops.db.session import create_engine, create_session_factory
from pulseops.logs import configure_logging
from pulseops.notifications.webhook import WebhookNotifier
from pulseops.security.transport import build_guarded_client
from pulseops.security.url_policy import DestinationPolicy
from pulseops.worker.runner import Worker

logger = logging.getLogger("pulseops.worker")

# Chave do advisory lock que garante um único worker por banco (ADR 0002).
WORKER_LOCK_KEY = 0x50554C53  # "PULS"


async def try_acquire_worker_lock(conn: AsyncConnection) -> bool:
    """Lock de sessão do PostgreSQL: só uma conexão por banco consegue segurá-lo."""
    got = await conn.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": WORKER_LOCK_KEY})
    await conn.commit()  # o lock é de sessão: continua valendo depois do commit
    return bool(got)


async def main() -> int:
    settings = Settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings.database_url, pool_size=settings.worker_concurrency + 5)
    sessions = create_session_factory(engine)
    clock = SystemClock()
    policy = DestinationPolicy(settings.allowed_port_set, settings.demo_allowlist)
    user_agent = f"PulseOps/{__version__} (+monitoramento)"

    # Conexão dedicada que segura o lock enquanto o processo vive.
    async with engine.connect() as lock_conn:
        if not await try_acquire_worker_lock(lock_conn):
            logger.error("outro worker já está rodando neste banco; apenas um é suportado")
            await engine.dispose()
            return 1

        check_client = build_guarded_client(
            policy, max_connections=settings.worker_concurrency, user_agent=user_agent
        )
        webhook_client = build_guarded_client(policy, max_connections=10, user_agent=user_agent)
        worker = Worker(
            sessions=sessions,
            checker=HttpChecker(check_client, clock),
            notifier=WebhookNotifier(
                webhook_client, clock, policy, settings.webhook_timeout_seconds
            ),
            clock=clock,
            settings=settings,
        )

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        try:
            await worker.run(stop)
        finally:
            await check_client.aclose()
            await webhook_client.aclose()
    await engine.dispose()
    logger.info("worker encerrado")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
