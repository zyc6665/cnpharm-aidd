"""时间工具。"""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """返回不带时区信息的 UTC 时间。"""
    return datetime.now(UTC).replace(tzinfo=None)


def utcnow_iso() -> str:
    """返回当前 UTC 时间的 ISO 字符串。"""
    return utcnow().isoformat()


def isoformat_z(value: datetime) -> str:
    """返回带 Z 后缀的 UTC ISO 字符串。"""
    return value.isoformat() + "Z"
