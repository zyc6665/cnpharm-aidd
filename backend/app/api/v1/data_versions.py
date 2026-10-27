"""数据版本查询 API（docs/04 §8.3、docs/18 G-11）。

本模块**只有读接口**：版本行由实体写入路径在各自事务里追加
（``domain_compounds.upsert_compound``、``targets.create_protein``、
``datasets.register_dataset``），不对外暴露写入端点——否则历史可以被伪造，
「只追加」这条规矩就落到 HTTP 层就断了。

两个 router 的分工与 targets/compounds/datasets 一致：

- ``project_router``（无 prefix，注册时挂 ``/projects``）：项目内的版本动态，
  跨实体类型的一览；
- ``router``（无 prefix）：单个实体（``entity_type`` + ``entity_id``）的历史与单版本。

鉴权沿用各实体**既有**的口径，不新造一套：化合物按「是否被当前用户可见项目引用」
（与 ``GET /compounds/{id}`` 同一条路径），蛋白走靶点读写角色，数据集走项目成员角色。
这样同一个实体在详情页和版本页不会出现「详情能看、历史不能看」的错位。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.exceptions import NotFoundException
from app.common.responses import paginated_response, success_response
from app.database.session import get_db
from app.models.users import User
from app.models.versions import (
    ENTITY_TYPE_COMPOUND,
    ENTITY_TYPE_DATASET,
    ENTITY_TYPE_PROTEIN,
    DataVersion,
)
from app.services import data_versions as versions_service
from app.services import datasets as datasets_service
from app.services import domain_compounds, domain_targets
from app.services.project_access import require_project_role

#: 项目内读角色（与 datasets/compounds 一致）。
READ_ROLES = ("owner", "editor", "runner", "viewer")

project_router = APIRouter()
router = APIRouter()


async def _require_compound_visible(
    db: AsyncSession, *, entity_id: str, user: User
) -> None:
    """化合物可见性：直接转交 ``domain_compounds.require_compound_read_access``。

    化合物是全局主数据、没有 ``project_id``，只能按「是否被当前用户可见的项目引用」
    判定；不可见时返回 404 而不是 403，避免把存在性当权限泄露。

    这里**不再自己实现**一遍：化合物详情、版本历史、版本差异三处若各写一份，
    口径迟早分叉（比如一处按 READ_ROLES、一处只判「是成员」，``runner`` 能读详情
    却读不到历史）。唯一实现放在服务层，本函数只保留历史调用点。

    已知取舍（**待产品口径确认，此处不改行为**）：一个从未被任何项目引用的化合物
    （只能经 import 产生，当前无入口能造出该状态）其版本历史对所有非管理员都是 404。
    要修就得先回答「无项目归属的主数据该由谁读」，那不是本模块能定的。
    """
    await domain_compounds.require_compound_read_access(
        db, compound_id=entity_id, user=user
    )


async def _require_entity_read_access(
    db: AsyncSession, *, entity_type: str, entity_id: str, user: User
) -> None:
    """按实体类型分派到既有的鉴权函数，不在本模块另立规则。

    已知取舍（**待产品口径确认，此处不改行为**）：删除数据集后，``data_versions``
    里的历史行仍保留（追加式账本不删历史是对的），但本函数走 ``load_dataset`` 会先
    抛 404，历史页因此不可达。要放开就得绕开 ``load_dataset`` 直接查版本行，那等于
    允许「已删除实体」的历史被读到——「已删除实体的历史是否可查」是产品口径问题，
    不是实现细节，故先如实 404 并在测试里固定该行为
    （``test_deleted_dataset_history_is_not_reachable``）。
    """
    if entity_type == ENTITY_TYPE_COMPOUND:
        await _require_compound_visible(db, entity_id=entity_id, user=user)
        return
    if entity_type == ENTITY_TYPE_PROTEIN:
        protein = await domain_targets.load_protein(db, entity_id)
        target = await domain_targets.protein_target(db, protein)
        await domain_targets.require_target_read_access(db, target=target, user=user)
        return
    if entity_type == ENTITY_TYPE_DATASET:
        dataset = await datasets_service.load_dataset(db, entity_id)
        await require_project_role(
            db,
            project_id=str(dataset.project_id),
            user=user,
            allowed_roles=READ_ROLES,
        )
        return
    # ``entity_type`` 的枚举校验在服务层做；到这里说明传了未知类型。
    raise NotFoundException("数据版本不存在")


@project_router.get("/{project_id}/data-versions", response_model=dict)
async def list_project_data_versions(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=versions_service.MAX_PAGE_SIZE),
    entity_type: str | None = Query(None, max_length=32),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目内的版本动态：本项目所有化合物/蛋白/数据集的版本行，最新的在前。"""
    await require_project_role(
        db, project_id=project_id, user=current_user, allowed_roles=READ_ROLES
    )
    records, total = await versions_service.list_project_versions(
        db,
        project_id=project_id,
        entity_type=entity_type,
        page=page,
        page_size=page_size,
    )
    return paginated_response(
        items=[versions_service.serialize_version(item) for item in records],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/data-versions/{entity_type}/{entity_id}/latest", response_model=dict)
async def get_latest_data_version(
    entity_type: str,
    entity_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """某个实体的最新版本。

    声明在 ``/{version}`` 之前：``version`` 声明为 ``int``，若顺序反过来，
    ``/latest`` 会先匹配到那条路由并被判 422，而不是落在这里。
    """
    await _require_entity_read_access(
        db, entity_type=entity_type, entity_id=entity_id, user=current_user
    )
    record = await db.scalar(
        select(DataVersion)
        .where(
            DataVersion.entity_type == entity_type,
            DataVersion.entity_id == str(entity_id),
        )
        .order_by(DataVersion.version.desc())
        .limit(1)
    )
    if record is None:
        raise NotFoundException("数据版本不存在")
    return success_response(data=versions_service.serialize_version(record))


@router.get("/data-versions/{entity_type}/{entity_id}", response_model=dict)
async def list_data_versions(
    entity_type: str,
    entity_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=versions_service.MAX_PAGE_SIZE),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """实体历史，按版本号倒序（最新在前）。"""
    await _require_entity_read_access(
        db, entity_type=entity_type, entity_id=entity_id, user=current_user
    )
    records, total = await versions_service.list_versions(
        db, entity_type=entity_type, entity_id=entity_id, page=page, page_size=page_size
    )
    return paginated_response(
        items=[versions_service.serialize_version(item) for item in records],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/data-versions/{entity_type}/{entity_id}/{version}", response_model=dict)
async def get_data_version(
    entity_type: str,
    entity_id: str,
    version: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """某个具体版本，**含**内容快照。不存在时 404，与实体详情同一口径。

    这一条是唯一返回 ``content`` 的版本读端点：列表与 ``/latest`` 用
    ``serialize_version``（不带快照，避免翻页时响应体翻倍），单版本按 id 取一行
    时调用方的目的通常就是「看这一版到底长什么样」，故用 ``serialize_version_detail``。
    """
    await _require_entity_read_access(
        db, entity_type=entity_type, entity_id=entity_id, user=current_user
    )
    record = await db.scalar(
        select(DataVersion).where(
            DataVersion.entity_type == entity_type,
            DataVersion.entity_id == str(entity_id),
            DataVersion.version == int(version),
        )
    )
    if record is None:
        raise NotFoundException("数据版本不存在")
    return success_response(data=versions_service.serialize_version_detail(record))


__all__ = ["project_router", "router"]
