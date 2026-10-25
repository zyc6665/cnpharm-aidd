"""时间工具。"""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """返回不带时区信息的 UTC 时间。"""
    return datetime.now(UTC).replace(tzinfo=None)


def utcfromtimestamp(timestamp: float) -> datetime:
    """将 Unix 时间戳转换为不带时区信息的 UTC 时间。"""
    return datetime.fromtimestamp(timestamp, UTC).replace(tzinfo=None)


def utcnow_iso() -> str:
    """返回当前 UTC 时间的 ISO 字符串。"""
    return utcnow().isoformat()


def isoformat_z(value: datetime) -> str:
    """返回带 Z 后缀的 UTC ISO 字符串。"""
    return value.isoformat() + "Z"


def isoformat_utc(value: datetime | None) -> str | None:
    """把库里的时间序列化成**带时区标识**的 UTC 字符串。

    库里所有时间列都是 naive UTC（``utcnow()`` 会 ``replace(tzinfo=None)``），
    直接 ``isoformat()`` 得到 ``2026-10-25T13:00:00`` —— 前端 ``new Date()`` 会按
    **本地时区**解释它，东八区用户看到的每个时间都晚 8 小时。

    这里统一补 ``Z``：对 naive 值视为 UTC，对 aware 值先归一到 UTC 再加 ``Z``。
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
