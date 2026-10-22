"""Criação do engine assíncrono e da fábrica de sessões."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

SessionFactory = async_sessionmaker[AsyncSession]


def create_engine(database_url: str, *, pool_size: int = 10) -> AsyncEngine:
    return create_async_engine(
        database_url,
        pool_size=pool_size,
        pool_pre_ping=True,  # descarta conexões mortas (por exemplo, após o banco reiniciar)
        connect_args={"connect_timeout": 5},
    )


def create_session_factory(engine: AsyncEngine) -> SessionFactory:
    # expire_on_commit=False: objetos continuam legíveis depois do commit, sem nova consulta.
    return async_sessionmaker(engine, expire_on_commit=False)
