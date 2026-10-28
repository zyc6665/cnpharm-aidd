"""数据集登记与查询用例（docs/04 §8、docs/05 §4.1）。

语义边界（务必别越界）：本模块**只登记已完成的导入结果**——``file_urn`` 指向
``files`` 表里已经存在的文件，``summary`` 是那次解析的产物。它不打开文件、不解析
SDF/CSV，也不创建任务；解析仍走既有 ``POST /projects/{id}/compounds:import``。

这样划界的原因：解析是重活且已有唯一入口（含去重、去噪、候选集生成），若数据集
登记再解析一遍，同一份文件会被解析两次、产生两套行数口径，追溯链会立刻断裂
（docs/04 §1「库内只存 urn 与 sha256」）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import NotFoundException, ValidationException
from app.files.file_records import is_file_usable
from app.models.files import File as FileModel
from app.models.uploads import DATASET_TYPES, DataFile, Dataset
from app.models.users import User
from app.models.versions import ENTITY_TYPE_DATASET, SOURCE_TYPE_IMPORT
from app.schemas.datasets import DatasetCreate
from app.services import data_versions
from app.services.domain_targets import urn_file_id


def serialize_dataset(dataset: Dataset, *, files: list | None = None) -> dict:
    """数据集的对外表示。

    ``files`` 可显式传入以复用已加载的关联集合；未传时读 ``dataset.files``
    （关系配了 ``lazy="selectin"``，查询时已一并加载，不会触发 N+1）。

    ``summary`` 同时承载「解析摘要」与「结构化属性字段」（docs/02 Q-03），原样返回。

    **非 ``file:`` urn 的兼容分支**：``file_urn`` 只有是 ``file:<file_id>`` 形态时，
    登记才会解析出 ``data_files`` 行；外部系统给的其它 urn 形态（如 ``oss://...``）
    仍可登记，但 ``files`` 会保持空数组 ``[]``——这就是登记接口接入 ``DataFile``
    之前的旧行为，刻意保留以免打断已有调用方与历史数据。
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
    """登记数据集。同名同项目视为重复登记，直接 422 而不是静默产生两条。

    ``file_urn`` 是 ``file:<file_id>`` 时会解析 ``files`` 表并落 ``data_files`` 行；
    其它 urn 形态保持「只登记不落 DataFile」的旧行为（见 ``serialize_dataset``）。
    """
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

    # ``summary`` 是结构化属性字段的承载面（docs/02 Q-03）：解析摘要 + 用户登记的
    # 结构化属性并入同一个 JSON 列，不新增 ``attributes`` 列。
    #
    # 合并顺序：``summary`` 赢。``summary`` 是既有契约字段——请求里显式给出的键必须
    # 原样回读（``test_summary_round_trips_verbatim`` 守着这条），且对结构化资产它
    # 承载机器解析摘要；``attributes`` 是为非结构资产补充键值的**附加面**，只应填补
    # ``summary`` 里没有的键，不能反过来把调用方明确给出的摘要键覆盖掉。
    summary = dict(data.attributes or {})
    summary.update(data.summary)

    dataset = Dataset(
        project_id=str(project_id),
        created_by=str(user.id),
        name=data.name,
        dataset_type=data.dataset_type,
        file_urn=data.file_urn,
        row_count=int(data.row_count),
        summary=summary,
    )
    db.add(dataset)
    await db.flush()

    # ``dataset.id`` 要 flush 之后才有，因此 DataFile 在 flush 之后再构造。
    data_file = await _materialize_data_file(
        db, project_id=str(project_id), dataset=dataset, urn=data.file_urn
    )
    if data_file is not None:
        db.add(data_file)
        await db.flush()

    # 版本行落在 commit 之前：``record_version`` 自己不 commit，若这里先提交再记账，
    # 记账失败会留下一个「有数据集、无版本」的静默缺口。
    await data_versions.record_version(
        db,
        entity_type=ENTITY_TYPE_DATASET,
        entity_id=str(dataset.id),
        source_type=SOURCE_TYPE_IMPORT,
        user=user,
        source_file_urn=data.file_urn,
        change_summary=f"登记数据集：{data.name}",
        content=_dataset_version_content(dataset),
    )
    await db.commit()
    # 重新按 selectinload 取回，保证 ``serialize_dataset`` 能安全读到 ``files``
    # （异步会话下访问未加载关系会抛 ``MissingGreenlet``）。
    result = await db.execute(
        select(Dataset)
        .where(Dataset.id == dataset.id)
        .options(selectinload(Dataset.files))
    )
    return result.scalar_one()


#: ``files.content_type`` 可能为空，也可能长于 ``data_files.file_type`` 的列宽。
_DEFAULT_FILE_TYPE = "application/octet-stream"


def _file_type(content_type: str | None) -> str:
    """把 ``files.content_type`` 映射成 ``data_files.file_type``（列宽 32）。

    SQLite 不校验 ``VARCHAR(32)`` 的长度而 Postgres 会拒绝，因此统一兜底并截断，
    避免同一段代码在测试库能跑、换到 PostgreSQL 就报错。
    """
    value = (content_type or "").strip() or _DEFAULT_FILE_TYPE
    return value[:32]


async def _materialize_data_file(
    db: AsyncSession, *, project_id: str, dataset: Dataset, urn: str
) -> DataFile | None:
    """把 ``file_urn`` 解析成 ``data_files`` 行；非 ``file:`` urn 返回 ``None``。

    解析复用 ``app.services.domain_targets`` 的 ``urn_file_id``，不另造一套规则：

    - ``urn`` 不是 ``file:`` 形态 → 返回 ``None``，保持「只登记不落 DataFile」的
      旧行为（外部系统的 ``oss://`` 等 urn 不能让登记失败）。
    - ``file:`` urn 指向的文件在 ``files`` 表里不存在 → ``ValidationException``，
      消息点明是 urn 无效。
    - 文件存在但 ``project_id`` 不同 → ``ValidationException``，消息点明跨项目。
    - 文件存在且属于本项目、但已软删除 / 已损坏 / 已过期 → ``ValidationException``。
      软删除与损坏的记录**仍留在 ``files`` 表里**（软删除要等物理清理、损坏只置标记），
      只校验「存在」会让用户拿到一个指向已删文件的数据集，一直到下载时才 404。
      这里直接复用 ``app.files.file_records.is_file_usable``，不另立一套「可用」判定——
      「能不能被新任务绑定」与「能不能被登记进数据集」是同一个问题。
    """
    file_id = urn_file_id(urn)
    if file_id is None:
        return None
    record = await db.get(FileModel, file_id)
    if record is None:
        raise ValidationException(f"file_urn 无效：files 表中不存在文件 {file_id}")
    if str(record.project_id) != str(project_id):
        raise ValidationException("file_urn 指向的文件不属于当前项目")
    if not is_file_usable(record):
        raise ValidationException(
            f"file_urn 指向的文件{_unusable_reason(record)}，无法登记为数据集文件"
        )
    return DataFile(
        dataset_id=dataset.id,
        urn=urn,
        file_name=record.filename,
        file_type=_file_type(record.content_type),
        size_bytes=int(record.size_bytes or 0),
        sha256=record.sha256,
        storage_tier="STANDARD",
    )


def _unusable_reason(file_record: Any) -> str:
    """只为报错措辞服务的诊断函数，**不是第二道判定闸门**。

    闸门是 ``is_file_usable``（见 ``_materialize_data_file``）；这里只在它已经判否之后
    把原因说清楚，好让调用方知道该重新上传还是该换文件。若将来 ``is_file_usable`` 增加
    新的不可用条件，本函数会退化成「已过期」，但不会改变放行/拒绝的结果。
    """
    if getattr(file_record, "deleted_at", None) is not None:
        return "已被删除"
    if bool(getattr(file_record, "is_corrupted", False)):
        return "已损坏"
    return "已过期"


def _dataset_version_content(dataset: Dataset) -> dict:
    """版本指纹的取样范围：``file_urn`` + 行数 + 解析摘要。

    ``name`` / ``dataset_type`` 是标签而非内容，改名不该产生新版本；``summary`` 是
    那次解析的产物，必须纳入，否则「同一份文件重新解析出不同结果」查不出来。
    """
    return {
        "file_urn": dataset.file_urn,
        "row_count": int(dataset.row_count or 0),
        "summary": dataset.summary or {},
    }


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
