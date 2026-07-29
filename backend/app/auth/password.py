# backend/app/auth/password.py
"""密码处理"""

import bcrypt

MAX_BCRYPT_PASSWORD_BYTES = 72


def _encode_password(password: str) -> bytes:
    """Encode passwords without silently changing their value."""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError("密码长度不能超过 72 个 UTF-8 字节")
    return password_bytes


def hash_password(password: str) -> str:
    """哈希密码"""
    password_bytes = _encode_password(password)
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    try:
        password_bytes = _encode_password(plain_password)
    except ValueError:
        return False
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)
