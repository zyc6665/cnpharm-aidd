"""merge decisions and uploads（收敛 PR1 / PR2 的双 head）

PR1（``20261027_01`` 研发决策记录）与 PR2（``20261027_02`` 分片上传与数据集）
都从 main 的 ``20261026_04`` 分叉。两个 PR 并行开发时各自是一条 head，直接
``alembic upgrade head`` 会报 "Multiple head revisions are present"。

本迁移只做一件事：把两条 head 收成一个。``upgrade``/``downgrade`` 都是 ``pass``——
没有任何 schema 变更，只改 DAG 拓扑。

注意：``20261027_01`` 由并行的 PR1 创建，单独 checkout PR2 分支时该 revision 文件
并不存在，此时 ``alembic heads`` 会解析失败（KeyError）。这是两分支真正合入 main
前的预期中间态；PR1 合入后即自动闭合。

Revision ID: 20261027_03
Revises: 20261027_01, 20261027_02
Create Date: 2026-10-27
"""

revision = "20261027_03"
down_revision = ("20261027_01", "20261027_02")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """两条 head 汇合，无 schema 变更。"""
    pass


def downgrade() -> None:
    """拆分回两条 head，无 schema 变更。"""
    pass
