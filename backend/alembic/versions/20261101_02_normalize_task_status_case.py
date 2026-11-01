"""把历史任务状态统一成大写枚举值

Revision ID: 20261101_02
Revises: 20261101_01
Create Date: 2026-11-01

## 为什么要做数据迁移

`TASK_STATUS` 的取值在「状态八态统一」那次改造中从**小写**（`pending`/`success`）
改成了**大写**（`PENDING`/`SUCCESS`，见 `app/common/enums.py`），但那一版只改了
代码常量，没有回填历史行。

后果不是报错，而是**静默漏算**：`GET /api/v1/tasks/counts` 用
`Task.status.in_(["PENDING", "QUEUED", "RUNNING"])` 分组统计，小写行一条也匹配不上。
本次实测就遇到过「`all` 有 200 条，但 running/needs_attention/recent_results 全是 0」——
工作台「我的待办」三张卡片全显示 0，而任务列表里明明有失败任务。

这类问题的共性：**查询不报错、页面不报错、数字就是不对**，靠人看页面基本发现不了。

## 做法

只把取值映射到规范形态，不做别的语义转换（不动 `queued` 与 `pending` 的区分）：

    pending -> PENDING, queued -> QUEUED, running -> RUNNING, success -> SUCCESS,
    failure -> FAILURE, canceled -> CANCELED, timeout -> TIMEOUT, rejected -> REJECTED

`WHERE status <> upper(status)` 保证：已经是规范值的行不被触碰（幂等，可重复执行），
也避免全表重写产生无谓的 WAL。

## downgrade

不回退。大写是规范形态，把数据改回小写只会重新制造缺陷；而且无法判断哪些行
原本是小写（迁移后两类行已无法区分）。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261101_02"
down_revision = "20261101_01"
branch_labels = None
depends_on = None

TABLE_NAME = "tasks"

#: 历史取值 -> 规范取值。只列会被 `upper()` 覆盖的项，写全是为了让读者一眼看清映射。
LEGACY_STATUS_MAP = {
    "pending": "PENDING",
    "queued": "QUEUED",
    "running": "RUNNING",
    "success": "SUCCESS",
    "failure": "FAILURE",
    "canceled": "CANCELED",
    "timeout": "TIMEOUT",
    "rejected": "REJECTED",
}


def _table_exists() -> bool:
    bind = op.get_bind()
    return TABLE_NAME in set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    if not _table_exists():
        return
    tasks = sa.table("tasks", sa.column("status", sa.String))
    op.execute(
        tasks.update()
        .where(tasks.c.status.is_not(None))
        .where(tasks.c.status != sa.func.upper(tasks.c.status))
        .values(status=sa.func.upper(tasks.c.status))
    )


def downgrade() -> None:
    # 有意留空：大写是规范形态，回退会重新制造「统计漏算」缺陷。
    pass
