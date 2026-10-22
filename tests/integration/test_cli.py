"""CLI de criação do operador (RF08.1)."""

import io

import pytest
from sqlalchemy import select

from pulseops import cli
from pulseops.db.models import Operator
from pulseops.db.session import SessionFactory


async def test_create_admin_from_stdin(
    sessions: SessionFactory,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("PULSEOPS_DATABASE_URL", database_url)
    monkeypatch.setattr("sys.stdin", io.StringIO("uma-senha-longa-ok\n"))
    # asyncio.run não pode ser chamado de dentro do loop do teste: roda numa thread.
    import asyncio

    code = await asyncio.to_thread(
        cli.main, ["create-admin", "--username", "amanda", "--password-stdin"]
    )
    assert code == 0 and "criado" in capsys.readouterr().out
    async with sessions() as session:
        operator = (await session.scalars(select(Operator))).one()
    assert operator.username == "amanda" and operator.password_hash.startswith("$argon2id$")

    monkeypatch.setattr("sys.stdin", io.StringIO("uma-senha-longa-ok\n"))
    assert (
        await asyncio.to_thread(
            cli.main, ["create-admin", "--username", "amanda", "--password-stdin"]
        )
        == 1
    )
    monkeypatch.setattr("sys.stdin", io.StringIO("uma-senha-longa-ok\n"))
    assert (
        await asyncio.to_thread(
            cli.main, ["create-admin", "--username", "amanda", "--password-stdin", "--exists-ok"]
        )
        == 0
    )


async def test_short_password_is_rejected(
    sessions: SessionFactory, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PULSEOPS_DATABASE_URL", database_url)
    monkeypatch.setattr("sys.stdin", io.StringIO("curta\n"))
    import asyncio

    assert (
        await asyncio.to_thread(cli.main, ["create-admin", "--username", "x12", "--password-stdin"])
        == 1
    )
