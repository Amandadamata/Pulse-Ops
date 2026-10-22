"""Operador, login e sessões (RF08, ADR 0008)."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from pulseops.db.models import Operator, OperatorSession
from pulseops.security.passwords import hash_password, verify_password


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_operator(
    session: AsyncSession, username: str, password: str, *, now: datetime
) -> Operator:
    username = username.strip()
    if not 3 <= len(username) <= 50:
        raise ValueError("o usuário precisa ter de 3 a 50 caracteres")
    if await session.scalar(select(Operator.id).where(Operator.username == username)):
        raise ValueError(f"o usuário {username!r} já existe")
    operator = Operator(username=username, password_hash=hash_password(password), created_at=now)
    session.add(operator)
    await session.flush()
    return operator


async def authenticate(session: AsyncSession, username: str, password: str) -> Operator | None:
    operator = await session.scalar(select(Operator).where(Operator.username == username.strip()))
    # verify_password roda mesmo sem usuário, para não revelar quais usuários existem pelo tempo.
    if verify_password(operator.password_hash if operator else None, password):
        return operator
    return None


@dataclass(frozen=True)
class NewSession:
    token: str  # vai para o cookie; o banco guarda só o hash
    csrf_token: str
    expires_at: datetime


async def start_session(
    session: AsyncSession, operator: Operator, *, now: datetime, ttl: timedelta
) -> NewSession:
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = now + ttl
    session.add(
        OperatorSession(
            token_hash=hash_token(token),
            operator_id=operator.id,
            csrf_token=csrf_token,
            created_at=now,
            expires_at=expires_at,
        )
    )
    # Aproveita o login para limpar sessões vencidas.
    await session.execute(delete(OperatorSession).where(OperatorSession.expires_at <= now))
    return NewSession(token, csrf_token, expires_at)


async def load_session(
    session: AsyncSession, token: str, *, now: datetime
) -> tuple[OperatorSession, Operator] | None:
    row = (
        await session.execute(
            select(OperatorSession, Operator)
            .join(Operator, Operator.id == OperatorSession.operator_id)
            .where(
                OperatorSession.token_hash == hash_token(token), OperatorSession.expires_at > now
            )
        )
    ).first()
    return (row[0], row[1]) if row else None


async def end_session(session: AsyncSession, token: str) -> None:
    await session.execute(
        delete(OperatorSession).where(OperatorSession.token_hash == hash_token(token))
    )
