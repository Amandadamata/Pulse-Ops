import pytest

from pulseops.security.passwords import hash_password, verify_password


def test_hash_is_argon2id_and_verifies() -> None:
    hashed = hash_password("uma senha bem longa")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "uma senha bem longa")
    assert not verify_password(hashed, "outra senha qualquer")


def test_short_password_is_rejected() -> None:
    with pytest.raises(ValueError):
        hash_password("curta")


def test_missing_user_never_verifies() -> None:
    assert verify_password(None, "pulseops-dummy-password") is False
    assert verify_password("não é um hash", "x") is False
