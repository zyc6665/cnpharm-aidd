"""数据集登记与查询用例（docs/04 §8、docs/05 §4.1）。

语义边界（务必别越界）：本模块**只登记已完成的导入结果**——``file_urn`` 指向
``files`` 表里已经存在的文件，``summary`` 是那次解析的产物。它不打开文件、不解析
SDF/CSV，也不创建任务；解析仍走既有 ``POST /projects/{id}/compounds:import``。

这样划界的原因：解析是重活且已有唯一入口（含去重、去噪、候选集生成），若数据集
登记再解析一遍，同一份文件会被解析两次、产生两套行数口径，追溯链会立刻断裂
（docs/04 §1「库内只存 urn 与 sha256」）。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import NotFoundException, ValidationException
from app.models.uploads import DATASET_TYPES, Dataset
from app.models.users import User
from app.schemas.datasets import DatasetCreate


def serialize_dataset(dataset: Dataset, *, files: list | None = None) -> dict:
    """数据集的对外表示。

    ``files`` 可显式传入以复用已加载的关联集合；未传时读 ``dataset.files``
    （关系配了 ``lazy="selectin"``，查询时已一并加载，不会触发 N+1）。
    """
    records = files if files is not None else list(getattr(dataset, "files", []) or [])
    return {
        "id": str(dataset.id),
        "projectId": str(dataset.project_id),
        "name": dataset.name,
        "datasetType": dataset.dataset_type,
        "fileUrn": dataset.file_urn,
        "rowCount": int(dataset.row_count or 0),
        "summary": dataset.summary or {},
        "importTaskId": dataset.import_task_id,
        "files": [
            {
                "id": str(item.id),
                "urn": item.urn,
                "fileName": item.file_name,
                "fileType": item.file_type,
                "sizeBytes": int(item.size_bytes or 0),
                "sha256": item.sha256,
                "storageTier": item.storage_tier,
            }
            for item in records
        ],
        "createdAt": dataset.created_at.isoformat() if dataset.created_at else None,
    }


async def register_dataset(
    db: AsyncSession, *, project_id: str, user: User, data: DatasetCreate
) -> Dataset:
    """登记数据集。同名同项目视为重复登记，直接 422 而不是静默产生两条。"""
    if data.dataset_type not in DATASET_TYPES:
        raise ValidationException(f"不支持的数据集类型: {data.dataset_type}")

    duplicate = await db.scalar(
        select(Dataset.id).where(
            Dataset.project_id == str(project_id),
            Dataset.name == data.name,
            Dataset.dataset_type == data.dataset_type,
        )
    )
    if duplicate is not None:
        raise ValidationException("同项目下已存在同名同类型的数据集")

    dataset = Dataset(
        project_id=str(project_id),
        created_by=str(user.id),
        name=data.name,
        dataset_type=data.dataset_type,
        file_urn=data.file_urn,
        row_count=int(data.row_count),
        summary=dict(data.summary),
    )
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)
    return dataset


async def list_datasets(
    db: AsyncSession,
    *,
    project_id: str,
    page: int,
    page_size: int,
    dataset_type: str | None = None,
) -> tuple[list[dict], int]:
    """项目内数据集分页列表，可按类型筛选；返回 (items, total)。"""
    conditions = [Dataset.project_id == str(project_id)]
    if dataset_type:
        conditions.append(Dataset.dataset_type == dataset_type)

    total = await db.scalar(select(func.count(Dataset.id)).where(*conditions))
    result = await db.execute(
        select(Dataset)
        .where(*conditions)
        .options(selectinload(Dataset.files))
        .order_by(Dataset.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [serialize_dataset(item) for item in result.scalars().all()]
    return items, int(total or 0)


async def load_dataset(db: AsyncSession, dataset_id: str) -> Dataset:
    """按 id 取数据集，不存在时 404。"""
    dataset = await db.scalar(
        select(Dataset)
        .where(Dataset.id == str(dataset_id))
        .options(selectinload(Dataset.files))
    )
    if dataset is None:
        raise NotFoundException("数据集不存在")
    return dataset


async def delete_dataset(db: AsyncSession, *, dataset: Dataset) -> None:
    """删除数据集登记记录。

    只删登记与 ``data_files`` 子行，**不删底层文件**——同一个文件可能被多个数据集
    或候选物引用，删文件会让追溯链指向空洞（files 的回收由生命周期任务负责）。
    """
    await db.delete(dataset)
    await db.commit()


__all__ = [
    "delete_dataset",
    "list_datasets",
    "load_dataset",
    "register_dataset",
    "serialize_dataset",
]
