"""Ambiente do Alembic: usa a mesma URL e os mesmos modelos da aplicação.

As migrações rodam de forma síncrona com o driver psycopg 3, o mesmo usado pela
aplicação no modo assíncrono.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from pulseops.config import Settings
from pulseops.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    # Permite que os testes passem uma URL própria via config.attributes.
    return str(config.attributes.get("database_url") or Settings().database_url)


def run_migrations_offline() -> None:
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
