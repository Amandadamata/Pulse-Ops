"""Linha de comando: `pulseops create-admin --username NOME`.

A senha é lida do terminal (sem eco) ou da entrada padrão com --password-stdin,
para não aparecer no histórico do shell nem na lista de processos.
"""

import argparse
import asyncio
import getpass
import sys

from pulseops.clock import SystemClock
from pulseops.config import Settings
from pulseops.db.session import create_engine, create_session_factory
from pulseops.services.auth import create_operator


async def _create_admin(username: str, password: str) -> None:
    engine = create_engine(Settings().database_url, pool_size=1)
    try:
        sessions = create_session_factory(engine)
        async with sessions.begin() as session:
            await create_operator(session, username, password, now=SystemClock().now())
    finally:
        await engine.dispose()


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Senha (mínimo 12 caracteres): ")
    if getpass.getpass("Repita a senha: ") != first:
        raise ValueError("as senhas não conferem")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pulseops")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin", help="cria o operador do PulseOps")
    admin.add_argument("--username", required=True)
    admin.add_argument("--password-stdin", action="store_true", help="lê a senha da entrada padrão")
    args = parser.parse_args(argv)

    try:
        password = _read_password(args.password_stdin)
        asyncio.run(_create_admin(args.username, password))
    except ValueError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    print(f"operador {args.username!r} criado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
