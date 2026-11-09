"""Creates the async engine and the session factory."""

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
        pool_pre_ping=True,  # drops dead connections (for example, after the database restarts)
        connect_args={"connect_timeout": 5},
    )


def create_session_factory(engine: AsyncEngine) -> SessionFactory:
    # expire_on_commit=False: objects stay readable after commit, without a new query.
    return async_sessionmaker(engine, expire_on_commit=False)
