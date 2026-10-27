"""任务状态机补齐 REJECTED 第 8 态（无 schema 变更，也无数据迁移）

对应验收偏差 B-2（``docs/18-项目验收报告.md`` §6.4）：规格 ``docs/03`` §3.4 与
``docs/04`` §6.1 要求八态
``CREATED / QUEUED / RUNNING / SUCCEEDED / FAILED / CANCELLED / TIMEOUT / REJECTED``，
``20261028_02`` 已补 ``QUEUED`` / ``TIMEOUT``，本次补最后一个 ``REJECTED``。

为什么没有 schema 变更
----------------------
``tasks.status`` 是 ``String(20)`` 且**没有 CHECK 约束**（全仓唯一的
``CheckConstraint`` 在 ``20261026_02`` 的 ``candidates`` 表上，与任务状态无关）。
``REJECTED`` 只有 8 个字符，远小于 20。因此加这个枚举值不需要改列类型、
改长度或加约束——加约束反而会让以后再加状态时多一次迁移。

为什么没有数据迁移
------------------
历史数据里不存在「当时被拒但被记成了别的状态」的行：
``_enforce_project_quota`` 在本次改动之前是**直接抛 429、不落库**的
（见 ``app/tasks/service.py`` 的 docstring：「被拦的提交不会留下 PENDING 空壳任务行」）。
也就是说历史库中根本没有可回填的拒绝记录，凭空造一批 ``REJECTED`` 行
等于伪造审计证据。

结论：历史行保持原状，``REJECTED`` 只对本次改动之后的新提交生效。
因此 ``upgrade()`` / ``downgrade()`` 都是幂等的空操作，仅用于让 alembic
版本链与代码改动对齐（保持单 head）。

Revision ID: 20261028_07
Revises: 20261028_06
Create Date: 2026-10-28
"""

from __future__ import annotations

revision = "20261028_07"
down_revision = "20261028_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """无需变更：状态列长度足够且无 CHECK 约束，历史数据不可判定。"""
    pass


def downgrade() -> None:
    """无需回滚：本迁移未修改任何 schema 或数据。"""
    pass
