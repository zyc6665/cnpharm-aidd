"""搜索关键字处理：LIKE 通配符转义与长度上限（P2 注入硬化）。

用户输入的 ``keyword`` 会拼进 ``%keyword%`` 交给 SQLAlchemy ``ilike``。若不转义，
``%`` 与 ``_`` 会被数据库当成通配符——用户输入单个 ``%`` 就会命中全表（既可能
拖垮数据库，也可配合其它条件做探测）。这里统一做两件事：

1. 用反斜杠转义 ``\\``、``%``、``_``，并让查询显式带 ``escape="\\\\"``；
2. 对所有搜索入口统一截断到 ``DEFAULT_KEYWORD_MAX_LENGTH`` 字符，避免超长关键字
   进入查询（路由层另有 ``Query(max_length=...)`` 做 422 前置校验）。
"""

from __future__ import annotations

#: 关键字最大长度（字符）。全站搜索入口统一使用，默认 200。
DEFAULT_KEYWORD_MAX_LENGTH = 200

#: LIKE 转义字符；需与调用处 ``.ilike(pattern, escape=LIKE_ESCAPE)`` 保持一致。
LIKE_ESCAPE = "\\"


def escape_like(value: str) -> str:
    """转义 LIKE 元字符：``\\``、``%``、``_`` 前加反斜杠。"""
    return (
        value.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )


def like_pattern(
    value: str,
    *,
    max_length: int = DEFAULT_KEYWORD_MAX_LENGTH,
) -> str:
    """构造 ``%<已转义关键字>%``，并先按 ``max_length`` 截断。

    调用方须以 ``.ilike(like_pattern(keyword), escape=LIKE_ESCAPE)`` 使用，
    否则转义字符不生效、``%`` 仍会被当通配符。
    """
    truncated = (value or "")[: int(max_length)]
    return f"%{escape_like(truncated)}%"


__all__ = [
    "DEFAULT_KEYWORD_MAX_LENGTH",
    "LIKE_ESCAPE",
    "escape_like",
    "like_pattern",
]
