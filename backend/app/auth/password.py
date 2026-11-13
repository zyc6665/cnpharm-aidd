# backend/app/auth/password.py
"""密码处理"""

import bcrypt

from app.pwdpolicy import (
    MAX_BCRYPT_PASSWORD_BYTES,
    MIN_PASSWORD_LENGTH,
    PASSWORD_TOO_LONG_MESSAGE,
    PASSWORD_TOO_SHORT_MESSAGE,
    validate_password_policy as _validate_password_policy,
)

#: 兼容既有调用点（schemas/users.py、api/v1/users.py 引用该名字）。
validate_password_policy = _validate_password_policy

__all__ = [
    "MIN_PASSWORD_LENGTH",
    "MAX_BCRYPT_PASSWORD_BYTES",
    "PASSWORD_TOO_SHORT_MESSAGE",
    "PASSWORD_TOO_LONG_MESSAGE",
    "validate_password_policy",
    "hash_password",
    "verify_password",
]


def _encode_password(password: str) -> bytes:
    """Encode passwords without silently changing their value."""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError(PASSWORD_TOO_LONG_MESSAGE)
    return password_bytes


def hash_password(password: str) -> str:
    """哈希密码"""
    password_bytes = _encode_password(password)
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    """验证密码。

    ``hashed_password`` 为 None（统一认证账号在平台侧无口令，见 auth_sso 开户逻辑）
    或库里存了畸形 hash 时一律返回 False——这两个入口都是「外部数据不对」，
    不该升级成 500。
    """
    if not hashed_password:
        return False
    try:
        password_bytes = _encode_password(plain_password)
        return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))
    except (TypeError, ValueError):
        return False
