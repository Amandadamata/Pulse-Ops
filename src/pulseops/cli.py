"""Command line: `pulseops create-admin --username NAME`.

The password is read from the terminal (without echo) or from standard input with
--password-stdin, so it never shows up in the shell history or the process list.
"""

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from pulseops.clock import SystemClock
from pulseops.config import Settings
from pulseops.db.models import Operator
from pulseops.db.session import create_engine, create_session_factory
from pulseops.services.auth import create_operator


async def _create_admin(username: str, password: str, *, exists_ok: bool) -> bool:
    """Returns False if the user already existed and `exists_ok` was requested."""
    engine = create_engine(Settings().database_url, pool_size=1)
    try:
        sessions = create_session_factory(engine)
        async with sessions.begin() as session:
            if exists_ok and await session.scalar(
                select(Operator.id).where(Operator.username == username.strip())
            ):
                return False
            await create_operator(session, username, password, now=SystemClock().now())
            return True
    finally:
        await engine.dispose()


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Password (at least 12 characters): ")
    if getpass.getpass("Repeat the password: ") != first:
        raise ValueError("the passwords do not match")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pulseops")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin", help="creates the PulseOps operator")
    admin.add_argument("--username", required=True)
    admin.add_argument(
        "--password-stdin", action="store_true", help="reads the password from standard input"
    )
    admin.add_argument(
        "--exists-ok",
        action="store_true",
        help="does not fail if the user already exists (used in the demo)",
    )
    args = parser.parse_args(argv)

    try:
        password = _read_password(args.password_stdin)
        created = asyncio.run(_create_admin(args.username, password, exists_ok=args.exists_ok))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"operator {args.username!r} {'created' if created else 'already existed'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
