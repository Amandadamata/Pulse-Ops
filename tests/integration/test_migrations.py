"""A migração cria o banco do zero e corresponde aos modelos."""

import psycopg
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

from pulseops.db.models import Base
from tests.conftest import TEST_DATABASE_URL, alembic_config

EXPECTED_TABLES = {
    "operators",
    "operator_sessions",
    "monitors",
    "checks",
    "incidents",
    "incident_events",
    "health_changes",
    "coverage_gaps",
    "alert_destinations",
    "alert_events",
    "deliveries",
    "delivery_attempts",
    "worker_heartbeats",
}


@pytest.fixture
def scratch_url() -> str:
    """Banco separado, criado vazio, só para este teste."""
    url = make_url(TEST_DATABASE_URL).set(database="pulseops_migration_test")
    admin = url.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute('DROP DATABASE IF EXISTS "pulseops_migration_test" WITH (FORCE)')
        conn.execute('CREATE DATABASE "pulseops_migration_test"')
    return url.render_as_string(hide_password=False)


def test_upgrade_on_empty_database_creates_all_tables(scratch_url: str) -> None:
    command.upgrade(alembic_config(scratch_url), "head")
    engine = create_engine(scratch_url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert tables >= EXPECTED_TABLES
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == [], f"modelos e migração divergem: {diff}"
    finally:
        engine.dispose()


def test_downgrade_and_upgrade_again(scratch_url: str) -> None:
    config = alembic_config(scratch_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    engine = create_engine(scratch_url)
    try:
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    finally:
        engine.dispose()
    command.upgrade(config, "head")
