import pytest

from app.auth.password import hash_password, verify_password


def test_hash_password_rejects_password_over_bcrypt_byte_limit():
    with pytest.raises(ValueError, match="72"):
        hash_password("密" * 25)


def test_verify_password_rejects_password_over_bcrypt_byte_limit():
    password_hash = hash_password("valid-password")

    assert verify_password("密" * 25, password_hash) is False
