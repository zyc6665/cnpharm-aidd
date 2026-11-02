"""Re-seed the LVpocket tool package now that an owner exists.

Revision ID: 20261102_01
Revises: 20261101_02

背景 / 根因
============
``20261030_01_lvpocket_model_package.py`` 定义并注册了
``lvpocket-pocket-prediction`` 工具包。但本地库的 ``alembic_version`` 已是
``20261101_02``（说明该 revision 在迁移链上确实“执行过”），``tools`` 表里却没有
这个工具。

根因不是“迁移没跑”，也不是“跑了但被后续迁移删掉 / 置为 disabled”，而是该迁移
``upgrade()`` 里的「无 owner 则 no-op」早退分支：

    owner_id = _resolve_owner_id(bind)
    if owner_id is None:
        return

迁移执行时库里还没有任何用户（第一条 admin 的 created_at 是 2026-10-30
08:37:36，晚于 20261030_01 的落库时间），于是它只记录了 revision、没有写任何行。

佐证：
* 同样使用「无 owner 则 return」的 ``20261029_01_mock_model_packages`` 注册的
  mock 工具也全部缺失；
* 而 ``20261031_09`` 在 admin 已存在之后（created_at 2026-10-31 02:11）写入的
  molp / msign / pocket2mol 都在库里。
即：这是 seed 阶段无 owner 的空操作，而非后续删除或禁用。

修复方式
========
不手写 INSERT。本迁移直接复用 ``20261030_01`` 模块里既有的 ``upgrade()`` 定义
（其中包含 ``_tool_config()`` / tool_package_manifest /幂等 upsert 逻辑），在 owner
已存在的当下重新执行一次，把 ``lvpocket-pocket-prediction`` 以 published /
is_public=true 真正写入库。该 upgrade 是幂等的：工具已存在则 UPDATE，不存在则
INSERT，因此在新鲜库上重复执行也不会产生重复行。

downgrade 为空操作：本迁移只是补一次数据落库，撤销它不应删掉一个正在被使用的
工具；如需彻底移除，沿用 20261030_01 的 downgrade 语义。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

revision = "20261102_01"
down_revision = "20261101_02"
branch_labels = None
depends_on = None


_ORIGINAL_MIGRATION = Path(__file__).with_name("20261030_01_lvpocket_model_package.py")


def _load_original_migration():
    """Load the original LVpocket migration module by file path.

    Alembic 按文件（而非 import）发现 revision，因此这里以独立模块名再次加载同一
    文件不会与其 revision 注册冲突；其 ``upgrade()`` 里使用的 ``alembic.op`` 是
    指向当前迁移上下文的代理，调用时会绑定到本次迁移的连接。
    """
    spec = importlib.util.spec_from_file_location(
        "_reseed_lvpocket_20261030_01", _ORIGINAL_MIGRATION
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载原始迁移文件: {_ORIGINAL_MIGRATION}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upgrade() -> None:
    # 直接复用原始迁移的注册逻辑（含 manifest 与 upsert），不重写 INSERT。
    _load_original_migration().upgrade()


def downgrade() -> None:
    # No-op：只补一次幂等 seed，撤销本迁移不应删除正在使用的工具。
    return
