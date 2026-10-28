"""Add ``tasks.retry_of`` — 任务重试来源（G-4，docs/04 §615，docs/12 TC-M6-06）。

**语义（为什么不是「新任务指向旧任务」）**：本仓库的重提是**就地复用同一个 task 行**——
``backend/app/api/v1/tasks.py`` 的 ``retry_task`` 调用 ``TaskStateMachine.retry(task)``，
只把 ``status`` 改回 ``PENDING``、``retry_count + 1``，并不新建一行。所以不存在「第二行」
可以让 ``retry_of`` 去指；「上一次执行」只是同一行上的一次 execution attempt
（只存在 ``task.extra_data["execution_attempt_id"]`` 里，是一串 32 位 hex，没有独立的
attempt 表，也没有 attempt→task 的映射可供引用）。

因此这里把 ``retry_of`` 定义为「**这条重试链的起点任务 id**」：首次重试时写入，
之后永不覆盖。就地复用同一行时，链起点就是本行自身，于是 ``retry_of == 自己的 id``，
语义退化为「本行是重试产物」的持久标记；若将来从别的任务派生出新行，它天然就是那条
新行的旧任务来源。**非重试产生的任务为 NULL**，故列可空——它是可选的重试归属信息，
不是主键也不是外键。

**为什么用 String(36) 而不是 UUID 类型**：与 ``tasks.id`` 等其他 id 列一致，沿用
``String(36)`` 存 uuid 的字符串形式，便于跨 SQLite/Postgres 统一。

``upgrade`` / ``downgrade`` 都幂等：先用 ``sa.inspect`` 判断列/索引是否已存在，避免重复执行
报错。与 ``20261028_06`` 等兄弟迁移一致，**先判断 ``tasks`` 表是否存在**——``tasks`` 由初始
基线迁移创建，若版本链被手工改过（例如 ``test_alembic_migration_dry_run`` 里的 legacy 恢复
场景），升级到本 revision 时表可能根本不存在，此时 ``get_columns`` 会抛 ``NoSuchTableError``，
应直接跳过。``downgrade`` 删列时在 SQLite 上用 ``op.batch_alter_table``（SQLite 不支持直接
``ALTER TABLE ... DROP COLUMN``）。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20261028_08"
down_revision = "20261028_07"
branch_labels = None
depends_on = None


_TABLE = "tasks"
_COLUMN = "retry_of"
_INDEX = "ix_tasks_retry_of"


def _table_names(bind) -> set[str]:
    """返回当前数据库已存在的表名集合。"""
    return set(sa.inspect(bind).get_table_names())


def _column_names(bind) -> set[str]:
    """返回 ``tasks`` 表当前已存在的列名集合（表不存在时返回空集）。"""
    if _TABLE not in _table_names(bind):
        return set()
    return {column["name"] for column in sa.inspect(bind).get_columns(_TABLE)}


def _index_names(bind) -> set[str]:
    """返回 ``tasks`` 表当前已存在的索引名集合（表不存在时返回空集）。"""
    if _TABLE not in _table_names(bind):
        return set()
    return {index["name"] for index in sa.inspect(bind).get_indexes(_TABLE)}


def upgrade() -> None:
    """加 ``retry_of`` 列与其索引（幂等；缺 ``tasks`` 表则跳过）。"""
    bind = op.get_bind()
    if _TABLE not in _table_names(bind):
        # ``tasks`` 由初始基线迁移创建；缺表说明版本链被手工改过（legacy 恢复场景），
        # 此时建列没有意义，直接跳过，避免 ``get_columns`` 抛 ``NoSuchTableError``。
        return
    if _COLUMN not in _column_names(bind):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(length=36), nullable=True))
    if _INDEX not in _index_names(bind):
        op.create_index(_INDEX, _TABLE, [_COLUMN])


def downgrade() -> None:
    """删索引与 ``retry_of`` 列（幂等；SQLite 走 batch 模式，缺 ``tasks`` 表则跳过）。"""
    bind = op.get_bind()
    if _TABLE not in _table_names(bind):
        return
    if _INDEX in _index_names(bind):
        op.drop_index(_INDEX, table_name=_TABLE)
    if _COLUMN in _column_names(bind):
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.drop_column(_COLUMN)
