"""统一数据资产检索：以 ``Artifact`` 为资产根，``dataset`` 合并两源。

设计取舍（Task 5 §7.3，报告里会写清）
------------------------------------
计划书要求「统一检索底层查 Artifact」。绝大多数资产类型（蛋白结构、口袋、配体、
分子表、MD 轨迹、运行报告、化合物集）的产出都以 ``Artifact`` 落库，直接查它即可。

``dataset`` 是唯一的双来源类型：
- ``datasets`` / ``data_files`` 领域表（``GET /projects/{id}/datasets``，登记的数据集）；
- ``artifact_type='dataset'`` 的 Artifact（通用输入上传的兜底落库，见
  ``frontend/src/composables/useWorkflowPersistence.ts``）。

只查任意一侧都会让用户看到自己刚登记/刚上传的数据「凭空消失」，因此 ``type=dataset``
取两源并集。**分页在 SQL 层完成**：把两表的 ``(source, item_id, sort_at)`` 用
``UNION ALL`` 合成子查询，再统一 ``ORDER BY sort_at DESC, item_id`` + LIMIT/OFFSET，
``total`` 用同一子查询 ``COUNT(*)``。选它而不是内存合并的理由：内存合并若「先各取
一页」，``total`` 会算错且翻页会重复/漏行；全量加载再切片虽能算对，但内存随数据量
线性增长。UNION ALL 让排序、分页、计数都在库里完成，且以 ``item_id`` 作为稳定兜底
排序键，``sort_at`` 相同时翻页也不会抖动。

蛋白主数据（``proteins`` / ``protein_structures``）**不**并入这里：本端点覆盖的是
「模型产出/上传的结构产物」，用户自行导入的蛋白主数据仍在「靶点与结构」页。这个
差异由前端蛋白 Tab 的说明文案承担，不在后端静默合并两套口径。

返回项统一带 ``source`` 字段（``artifact`` / ``dataset``），前端据它区分语义（例如
数据集 Tab 里 ``source=artifact`` 的行标记为「上传文件」而非「登记数据集」）。
"""

from __future__ import annotations

from sqlalchemy import func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.artifact_standards.asset_types import is_asset_artifact_type
from app.common.exceptions import ValidationException
from app.common.time import utcnow
from app.models.artifacts import Artifact, ArtifactVersion, ArtifactVersionFile
from app.models.uploads import Dataset
from app.services.datasets import serialize_dataset

#: 数据集在数据资产页是一个 Tab，同时也是资产枚举的一员；检索时额外合并领域表。
DATASET_ASSET_TYPE = "dataset"


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _artifact_asset(artifact: Artifact) -> dict:
    version = artifact.latest_version
    return {
        "id": artifact.id,
        "asset_type": artifact.artifact_type,
        "name": artifact.name,
        "description": artifact.description,
        "source": "artifact",
        "latest_version_id": artifact.latest_version_id,
        "created_at": _iso(artifact.created_at),
        "updated_at": _iso(artifact.updated_at),
        "metadata": {
            "semanticType": artifact.semantic_type,
            "standardType": artifact.standard_type,
            "standardVersion": artifact.standard_version,
            "filename": version.filename if version else None,
            "contentType": version.content_type if version else None,
            "sizeBytes": version.size_bytes if version else None,
        },
    }


def _dataset_asset(dataset: dict) -> dict:
    return {
        "id": dataset["id"],
        "asset_type": DATASET_ASSET_TYPE,
        "name": dataset["name"],
        "description": None,
        "source": "dataset",
        "latest_version_id": None,
        "created_at": dataset.get("createdAt"),
        "updated_at": dataset.get("createdAt"),
        "metadata": {
            "datasetType": dataset.get("datasetType"),
            "rowCount": dataset.get("rowCount"),
            "fileCount": len(dataset.get("files") or []),
            "summary": dataset.get("summary") or {},
        },
    }


def _artifact_keys_select(*, project_id: str, artifact_type: str | None):
    """可见 Artifact 的 (source, item_id, sort_at) 行。

    「可见」= 有 latest_version、状态 available、未过期。此前是在 Python 侧过滤，
    现在必须下推到 SQL，否则 UNION 分页的 total/翻页会把不可见行算进去。
    """
    version = aliased(ArtifactVersion)
    stmt = (
        select(
            literal("artifact").label("source"),
            Artifact.id.label("item_id"),
            Artifact.updated_at.label("sort_at"),
        )
        .join(version, Artifact.latest_version_id == version.id)
        .where(
            Artifact.project_id == str(project_id),
            version.status == "available",
            or_(version.expires_at.is_(None), version.expires_at > utcnow()),
        )
    )
    if artifact_type:
        stmt = stmt.where(Artifact.artifact_type == artifact_type)
    return stmt


def _dataset_keys_select(*, project_id: str):
    return select(
        literal("dataset").label("source"),
        Dataset.id.label("item_id"),
        Dataset.created_at.label("sort_at"),
    ).where(Dataset.project_id == str(project_id))


async def _page_keys(
    db: AsyncSession,
    *,
    project_id: str,
    artifact_type: str | None,
    page: int,
    page_size: int,
):
    """在 SQL 层对两源做 UNION ALL 后统一排序分页，返回 (当前页 key 行, total)。"""
    combined = _artifact_keys_select(
        project_id=project_id, artifact_type=artifact_type
    )
    if artifact_type is None or artifact_type == DATASET_ASSET_TYPE:
        combined = combined.union_all(_dataset_keys_select(project_id=project_id))

    keys = combined.subquery("asset_keys")
    total = int(await db.scalar(select(func.count()).select_from(keys)) or 0)
    rows = (
        await db.execute(
            select(keys.c.source, keys.c.item_id)
            .order_by(keys.c.sort_at.desc(), keys.c.item_id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return rows, total


async def _hydrate_page(db: AsyncSession, rows) -> list[dict]:
    artifact_ids = [row.item_id for row in rows if row.source == "artifact"]
    dataset_ids = [row.item_id for row in rows if row.source == "dataset"]

    artifacts: dict[str, dict] = {}
    if artifact_ids:
        result = await db.execute(
            select(Artifact)
            .where(Artifact.id.in_(artifact_ids))
            .options(
                selectinload(Artifact.latest_version)
                .selectinload(ArtifactVersion.files)
                .selectinload(ArtifactVersionFile.file),
            )
        )
        artifacts = {item.id: _artifact_asset(item) for item in result.scalars().all()}

    datasets: dict[str, dict] = {}
    if dataset_ids:
        result = await db.execute(select(Dataset).where(Dataset.id.in_(dataset_ids)))
        datasets = {
            item.id: _dataset_asset(serialize_dataset(item))
            for item in result.scalars().all()
        }

    items: list[dict] = []
    for row in rows:
        bucket = artifacts if row.source == "artifact" else datasets
        item = bucket.get(row.item_id)
        if item is not None:
            items.append(item)
    return items


def _validate_asset_type(asset_type: str | None) -> None:
    if asset_type is None or asset_type == DATASET_ASSET_TYPE:
        return
    if not is_asset_artifact_type(asset_type):
        raise ValidationException(f"不支持的资产类型: {asset_type}")


async def list_project_assets(
    db: AsyncSession,
    *,
    project_id: str,
    asset_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    """按 ``type`` 检索项目资产，返回 (当前页 items, 过滤后总数)。

    - ``type=dataset``：``datasets`` 领域表 **与** ``artifact_type='dataset'`` 的
      Artifact 两源合并（见模块 docstring 的分页说明）。
    - 其它 8 类：只查 ``Artifact``。
    - ``None``：全部 Artifact + 全部数据集，两源合并混排。
    """
    _validate_asset_type(asset_type)
    rows, total = await _page_keys(
        db,
        project_id=project_id,
        artifact_type=asset_type,
        page=page,
        page_size=page_size,
    )
    items = await _hydrate_page(db, rows)
    return items, total


__all__ = ["DATASET_ASSET_TYPE", "list_project_assets"]
