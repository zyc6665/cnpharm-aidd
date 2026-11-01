# backend/app/pwd_policy.py
"""口令策略常量与校验（无第三方依赖，避免与 schemas/auth 形成循环导入）。

放在应用顶层（而非 ``app.auth`` / ``app.common``）是刻意的：``app.schemas.users``
在导入期就需要这些常量，而 ``app.auth`` / ``app.common`` 的包 ``__init__`` 会反向
导入 schemas，造成 partially initialized module 循环。
"""

MIN_PASSWORD_LENGTH = 12

#: bcrypt 只取前 72 字节；超过即拒绝，绝不静默截断（否则不同长口令等价）。
MAX_BCRYPT_PASSWORD_BYTES = 72

#: 统一错误文案，前后端提示一致。
PASSWORD_TOO_SHORT_MESSAGE = f"口令长度不能少于 {MIN_PASSWORD_LENGTH} 个字符"
PASSWORD_TOO_LONG_MESSAGE = (
    f"口令长度不能超过 {MAX_BCRYPT_PASSWORD_BYTES} 个 UTF-8 字节"
)


def validate_password_policy(password: str) -> str:
    """校验口令策略（最小长度 + bcrypt 72 字节上限），返回原值。

    供 Pydantic ``field_validator`` 复用；抛 ``ValueError`` 会被 Pydantic 转成 422
    业务校验错误，而不是在 hash 阶段抛未捕获异常变成 500。
    """
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise ValueError(PASSWORD_TOO_SHORT_MESSAGE)
    if len((password or "").encode("utf-8")) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError(PASSWORD_TOO_LONG_MESSAGE)
    return password
