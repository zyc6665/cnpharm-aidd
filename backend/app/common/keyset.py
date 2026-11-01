# backend/app/common/keyset.py
"""游标（keyset）分页。

**为什么要有这东西**：`LIMIT 20 OFFSET 100000` 不是「跳过 10 万行」，而是让数据库
把前 10 万行**逐行产出来再丢掉**——页越深越慢，且与页深成正比。任务列表与审计日志
都是只增不改的表，翻到深页时这个开销会盖过真正的查询。

游标分页改成「从上一页最后一行的位置继续」，代价与页深无关：

    WHERE created_at < :last_ts OR (created_at = :last_ts AND id < :last_id)
    ORDER BY created_at DESC, id DESC LIMIT :n

配合 ``(created_at DESC, id DESC)`` 或等价的 ``(created_at, id)`` 复合索引，
数据库只需索引 seek + 顺序取 n 行。

**排序键必须是全序**：只按 ``created_at`` 排序时同一毫秒的多行顺序不确定，翻页会
漏行或重复。所以游标里一定带主键作第二排序键（``id DESC``）。

契约（与前端约定，见 ``docs/20`` §5.13）：

* 不传 ``cursor`` → 原有 ``page``/``page_size`` + ``total`` 行为完全不变；
* 传 ``cursor`` → **不再计算 total**（算 total 与深分页同代价，会把这轮优化的收益
  抵掉），响应里给 ``nextCursor`` 与 ``hasMore``。
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import tuple_

from app.common.exceptions import ValidationException


def _encode_scalar(value: Any) -> Any:
    if isinstance(value, datetime):
        # 统一成 naive UTC ISO（库里的时间列都是 naive UTC，见 app.common.time）。
        return {"t": value.replace(tzinfo=None).isoformat()}
    return value


def _decode_scalar(value: Any) -> Any:
    if isinstance(value, dict) and "t" in value:
        return datetime.fromisoformat(str(value["t"]))
    return value


def encode_cursor(values: Sequence[Any]) -> str:
    """把一行的排序键编码成不透明字符串（带 ``~`` 前缀，便于识别与将来换实现）。"""
    payload = {"v": [_encode_scalar(value) for value in values]}
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "~" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> list[Any]:
    """解码游标；任何不合法输入都抛 422，而不是让 SQL 去撞类型错误。"""
    text = cursor[1:] if cursor.startswith("~") else cursor
    try:
        padded = text + "=" * (-len(text) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        values = payload["v"]
        if not isinstance(values, list) or len(values) != 2:
            raise ValueError("cursor must carry exactly two values")
    except Exception as exc:  # noqa: BLE001 - 统一转成对外可读的 422
        raise ValidationException("分页游标无效，请从第一页重新开始") from exc
    return [_decode_scalar(value) for value in values]


def apply_desc_keyset(statement, *, timestamp_column, id_column, cursor: str | None):
    """在「``ORDER BY timestamp DESC, id DESC``」的查询上加游标条件。

    返回 ``(statement, last_row_keys)``；``cursor`` 为 None 时原样返回。
    """
    if not cursor:
        return statement, None
    last_timestamp, last_id = decode_cursor(cursor)

    # 必须写成行值比较 `(ts, id) < (?, ?)`，不能展开成
    # `ts < ? OR (ts = ? AND id < ?)`：后者 SQLite 与 PostgreSQL 都**用不上索引
    # 区间**，退化成整段索引全扫（20 万行实测：展开式 10~21ms 且随页深增长，
    # 行值式 0.14~0.18ms 恒定）。同一份数据、同一个索引，写法差 60 倍。
    condition = tuple_(timestamp_column, id_column) < tuple_(last_timestamp, last_id)
    return statement.where(condition), (last_timestamp, last_id)


def next_cursor(rows: Sequence[Any], *, timestamp_attr: str, id_attr: str, limit: int) -> str | None:
    """从「多取一条」的结果集里产下一页游标。

    调用方应以 ``limit + 1`` 查询：多出来的那条只用来判断 ``hasMore``，
    不返回给客户端，也不参与游标计算。
    """
    if len(rows) <= limit:
        return None
    last = rows[limit - 1]
    return encode_cursor([getattr(last, timestamp_attr), getattr(last, id_attr)])
