"""任务状态机补齐 QUEUED / TIMEOUT（无 schema 变更，也无数据迁移）

对应验收偏差 B-2（``docs/18-项目验收报告.md`` §6.4）：规格 ``docs/03`` §3.4 与
``docs/01`` §10.2 要求八态
``CREATED → QUEUED → RUNNING → SUCCEEDED / FAILED / CANCELLED / TIMEOUT``，
而代码里只有五态。本次在 ``app/models/tasks.py::TaskStatus`` 里补上
``QUEUED`` 与 ``TIMEOUT``，并同步状态机、执行器与前端词表。

为什么没有 schema 变更
----------------------
``tasks.status`` 是 ``String(20)``（见 ``20261026_*`` 初始迁移与
``app/models/tasks.py``）。最长的新值 ``TIMEOUT`` 只有 7 个字符、``QUEUED``
6 个字符，都远小于 20，因此**不需要**改列类型、改长度或加约束。
``task_execution_records.status`` 是 ``String(32)``，新增的执行态
``timeout`` 同样放得下。

为什么没有数据迁移
------------------
历史数据里状态只有 ``PENDING`` / ``RUNNING`` / ``SUCCESS`` / ``FAILURE`` /
``CANCELED``，**没有任何行能被可靠地判定为「当时其实在排队」或「当时其实
超时」**：

* ``PENDING`` 同时被「刚创建、尚未分发」和「资源不足重新入队」两条路径写入
  （见 ``app/tasks/service.py`` 与 ``app/worker/tasks.py`` 的重排分支），
  库里没有任何区分二者的字段。把 ``PENDING`` 批量改成 ``QUEUED`` 会连带
  改写「新建未调度」的行，属于凭空造数据。
* 旧代码里超时是被包装成普通 ``TaskExecutionError`` 落的 ``FAILURE``
  （``docker.py`` / ``python_script.py`` / ``kubernetes_job.py`` /
  ``ssh_job.py`` 此前都 ``raise TaskExecutionError("... execution timeout")``），
   错误文本是唯一线索，但它属于日志/展示层文案，不可作为状态迁移依据。

结论：历史行保持原状，新状态只对本次改动之后产生的状态流转生效。
因此本迁移的 ``upgrade()`` / ``downgrade()`` 都是幂等的空操作，仅用于让
alembic 版本链与本次代码改动对齐（保持单 head）。

Revision ID: 20261028_02
Revises: 20261028_01
Create Date: 2026-10-28
"""

from __future__ import annotations

revision = "20261028_02"
down_revision = "20261028_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """无需变更：状态列长度足够，历史数据不可判定，故不迁移。"""
    pass


def downgrade() -> None:
    """无需回滚：本迁移未修改任何 schema 或数据。"""
    pass
