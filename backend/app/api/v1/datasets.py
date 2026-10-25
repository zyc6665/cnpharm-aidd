"""数据集登记与查询 API（docs/05 §4.1、docs/04 §8）。

两个 router 的分工与 targets/compounds 一致：

- ``project_router``（无 prefix，注册时挂 ``/projects``）：项目内数据集集合；
- ``router``（无 prefix）：单个数据集的读写。

领域语义在 ``app.services.datasets``；本模块只做权限、分页与响应包装。
读角色含 runner/viewer，写角色只有 owner/editor。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.responses import paginated_response, success_response
from app.database.session import get_db
from app.models.users import User
from app.schemas.datasets import DatasetCreate
from app.services import datasets as datasets_service
from app.services.project_access import require_project_role

#: 项目内读角色：具备只读访问的四种成员（docs/04 §3 角色矩阵）。
READ_ROLES = ("owner", "editor", "runner", "viewer")
#: 项目内写角色：能新增/删除数据集登记。
WRITE_ROLES = ("owner", "editor")

project_router = APIRouter()
router = APIRouter()


@project_router.get("/{project_id}/datasets", response_model=dict)
async def list_project_datasets(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    dataset_type: str | None = Query(None, max_length=32),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目内数据集列表，支持按 ``dataset_type`` 筛选（docs/06 P-12 数据资产）。"""
    await require_project_role(
        db, project_id=project_id, user=current_user, allowed_roles=READ_ROLES
    )
    items, total = await datasets_service.list_datasets(
        db,
        project_id=project_id,
        page=page,
        page_size=page_size,
        dataset_type=dataset_type,
    )
    return paginated_response(
        items=items, total=total, page=page, page_size=page_size
    )


@project_router.post("/{project_id}/datasets", response_model=dict)
async def create_project_dataset(
    project_id: str,
    data: DatasetCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """登记一个已完成的导入结果（``file_urn`` + ``summary``），**不重新解析文件**。"""
    await require_project_role(
        db, project_id=project_id, user=current_user, allowed_roles=WRITE_ROLES
    )
    dataset = await datasets_service.register_dataset(
        db, project_id=project_id, user=current_user, data=data
    )
    return success_response(datasets_service.serialize_dataset(dataset))


@router.get("/datasets/{dataset_id}", response_model=dict)
async def get_dataset(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """数据集详情。跨项目直达返回 404，不把存在性当 403 暴露。"""
    dataset = await datasets_service.load_dataset(db, dataset_id)
    await require_project_role(
        db,
        project_id=str(dataset.project_id),
        user=current_user,
        allowed_roles=READ_ROLES,
    )
    return success_response(datasets_service.serialize_dataset(dataset))


@router.delete("/datasets/{dataset_id}", response_model=dict)
async def remove_dataset(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除数据集登记（不删底层文件，文件回收走生命周期任务）。"""
    dataset = await datasets_service.load_dataset(db, dataset_id)
    await require_project_role(
        db,
        project_id=str(dataset.project_id),
        user=current_user,
        allowed_roles=WRITE_ROLES,
    )
    await datasets_service.delete_dataset(db, dataset=dataset)
    return success_response({"id": dataset_id, "deleted": True})


__all__ = ["project_router", "router"]
