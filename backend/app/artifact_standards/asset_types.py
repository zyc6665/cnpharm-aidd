"""资产根 ``Artifact.artifact_type`` 的受控类型枚举（单一真源）。

``Artifact`` 是项目内所有「资产」的统一根：一份逻辑资产的**身份**，版本是其按运行
追加的记录。为了让「数据资产页能按类别稳定检索」，也为了让下游（绑定解析、谱系、
前端枚举）拿到的是有限、可穷举的类型集合，这里把 ``artifact_type`` 收敛为 8 个受控
值，本模块是这 8 个取值的唯一真源：

- 模型层 CHECK 约束（``app.models.artifacts``）从这里取 SQL 片段；
- Pydantic 入口校验（``app.schemas.artifacts``）从这里取集合；
- Alembic 迁移 ``20261030_07`` 从这里取列表与历史归一名；
- 前端枚举生成器 ``scripts/gen_frontend_enums.py`` 从这里生成 TS 常量。

为什么不放进 ``app/common/enums.py``：``app/common/enums.py`` 里曾有一个供前端
ArtifactRenderer 选渲染组件的「渲染分类」枚举（含 ``pocket_result``/``file`` 等历史
别名），语义与这里的「资产根类型」不同；两者混用会让「渲染分类」和「资产分类」再次
纠缠。Task 5 已把渲染分派也统一到这个 8 值资产枚举（见前端
``components/artifacts/registry.ts``），旧的渲染分类枚举因此删除，这里成为唯一真源，
命名保持 ``ASSET_ARTIFACT_TYPE``。
"""

from __future__ import annotations

from .types import LEGACY_SEMANTIC_TYPE_ALIASES

#: 8 个受控资产类型（顺序即前端生成/展示顺序）。
ASSET_ARTIFACT_TYPES: tuple[str, ...] = (
    "compound_set",
    "protein_structure",
    "binding_pocket",
    "ligand_structure",
    "molecule_table",
    "md_trajectory",
    "run_report",
    "dataset",
)

#: 快速成员判断用的不可变集合。
ASSET_ARTIFACT_TYPE_SET = frozenset(ASSET_ARTIFACT_TYPES)

#: 历史写入口可能出现的旧值 → 合法资产类型。
#:
#: 由标准别名单 ``LEGACY_SEMANTIC_TYPE_ALIASES`` 派生（``protein_pdb``、
#: ``database_query_result``… → 对应标准类型），另补两个渲染分类里的旧名：
#: ``pocket_result`` → ``binding_pocket``、``file`` → ``run_report``。
#: 迁移时用它对历史值做**语义等价归一**，而不是丢弃数据；归不动的值会在探测阶段显式
#: 报错，交给人确认。
LEGACY_ASSET_TYPE_ALIASES: dict[str, str] = {
    alias: ref.split("@", 1)[0]
    for alias, ref in LEGACY_SEMANTIC_TYPE_ALIASES.items()
}
LEGACY_ASSET_TYPE_ALIASES.update(
    {
        "pocket_result": "binding_pocket",
        "file": "run_report",
    }
)

#: 供模型 CHECK 约束与 Alembic 迁移共用的 SQL 片段。
ASSET_ARTIFACT_TYPE_CHECK_SQL = "artifact_type IN (" + ", ".join(
    f"'{value}'" for value in ASSET_ARTIFACT_TYPES
) + ")"


def is_asset_artifact_type(value: object) -> bool:
    """``value`` 是否恰为 8 个受控类型之一（不做别名归一）。"""
    return isinstance(value, str) and value in ASSET_ARTIFACT_TYPE_SET


def normalize_asset_artifact_type(value: object) -> str | None:
    """把历史/别名/``type@version`` 写法归一为 8 值之一。

    无法归一时返回 ``None``——调用方（迁移探测）据此显式告警，绝不静默改写或丢弃。
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if candidate in ASSET_ARTIFACT_TYPE_SET:
        return candidate
    if candidate in LEGACY_ASSET_TYPE_ALIASES:
        return LEGACY_ASSET_TYPE_ALIASES[candidate]
    if "@" in candidate:
        base = candidate.split("@", 1)[0]
        if base in ASSET_ARTIFACT_TYPE_SET:
            return base
    return None


__all__ = [
    "ASSET_ARTIFACT_TYPES",
    "ASSET_ARTIFACT_TYPE_SET",
    "ASSET_ARTIFACT_TYPE_CHECK_SQL",
    "LEGACY_ASSET_TYPE_ALIASES",
    "is_asset_artifact_type",
    "normalize_asset_artifact_type",
]
