"""Hash de senha com Argon2id (biblioteca argon2-cffi, parâmetros padrão dela)."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_PASSWORD_LENGTH = 12

_hasher = PasswordHasher()
# Hash de uma senha qualquer, usado quando o usuário não existe: assim o login de um
# usuário inexistente leva o mesmo tempo que o de uma senha errada.
_DUMMY_HASH = _hasher.hash("pulseops-dummy-password")


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"a senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres")
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False
