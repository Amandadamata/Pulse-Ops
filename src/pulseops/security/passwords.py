"""Password hashing with Argon2id (argon2-cffi library, with its default parameters)."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_PASSWORD_LENGTH = 12

_hasher = PasswordHasher()
# Hash of an arbitrary password, used when the user does not exist: this way, logging in as a
# user that does not exist takes the same time as a wrong password.
_DUMMY_HASH = _hasher.hash("pulseops-dummy-password")


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"the password must have at least {MIN_PASSWORD_LENGTH} characters")
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError, ValueError):
        # A corrupted hash in the database (for example, text with accents) raises
        # UnicodeEncodeError, a subclass of ValueError: we treat it as an invalid password.
        return False
