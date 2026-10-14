"""工具版本管理路由。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.tool_route_utils import (
    require_tool_read_access,
    serialize_public_tool_version,
)
from app.auth.dependencies import get_admin_user, get_current_user_optional
from app.common.exceptions import NotFoundException, ValidationException
from app.common.responses import success_response
from app.database.session import get_db
from app.models.tools import Tool, ToolVersion
from app.models.users import User
from app.schemas.tasks import TaskCreate, ToolVersionSmokeCreate
from app.tasks.direct_runner import direct_task_runner
from app.tasks.service import create_and_schedule_tool_task
from app.tools.version_manager import ToolVersionManager, VersionError

router = APIRouter()

LEGACY_TOOL_VERSION_REGISTRATION_GONE_DETAIL = (
    "旧工具版本注册入口已下线，请从已发布 Tool Package 注册 Kubernetes 版本"
)


@router.get("/{tool_id}/versions", response_model=dict)
async def list_tool_versions(
    tool_id: str,
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    tool = await db.get(Tool, tool_id)
    if tool is None:
        raise NotFoundException("工具不存在")
    require_tool_read_access(tool, current_user)
    versions = (
        await db.execute(
            select(ToolVersion)
            .where(ToolVersion.tool_id == tool_id)
            .order_by(ToolVersion.created_at.desc())
        )
    ).scalars().all()
    return success_response(
        data=[
            serialize_public_tool_version(version)
            for version in versions
        ]
    )


@router.post("/{tool_id}/versions", response_model=dict)
async def create_tool_version(
    tool_id: str,
    current_user: User = Depends(get_admin_user),
):
    raise HTTPException(
        status_code=410,
        detail=LEGACY_TOOL_VERSION_REGISTRATION_GONE_DETAIL,
    )


@router.post("/{tool_id}/versions/{version_id}/smoke", response_model=dict)
async def smoke_tool_version(
    tool_id: str,
    version_id: str,
    request: ToolVersionSmokeCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    tool = await db.get(Tool, tool_id)
    if tool is None:
        raise NotFoundException("工具不存在")
    version = await db.get(ToolVersion, version_id)
    if version is None or version.tool_id != tool.id:
        raise NotFoundException("工具版本不存在")
    if version.deprecated:
        raise ValidationException("已废弃的工具版本不能执行 smoke")
    if version.is_active:
        raise ValidationException("Smoke 仅适用于尚未激活的候选版本")
    if (version.config or {}).get("type") != "k8s_job":
        raise ValidationException("Smoke 仅支持 Kubernetes 候选版本")

    task_data = TaskCreate(
        name=request.name or f"K8s smoke: {tool.name} {version.version}",
        project_id=request.project_id,
        tool_id=tool.id,
        tool_version_id=version.id,
        params=request.params,
        file_ids=request.file_ids,
        input_bindings=request.input_bindings,
        standard_input_uploads=request.standard_input_uploads,
        priority="normal",
    )
    task = await create_and_schedule_tool_task(
        db=db,
        current_user=current_user,
        task_data=task_data,
        direct_runner=direct_task_runner,
        extra_data={"run_kind": "tool_version_smoke"},
        allow_inactive_candidate=True,
    )
    return success_response(
        data={
            "task_id": task.id,
            "tool_id": tool.id,
            "tool_version_id": version.id,
            "status": task.status,
            "run_kind": "tool_version_smoke",
        },
        message="候选版本 smoke 任务已提交",
    )


@router.post("/{tool_id}/versions/{version_id}/promote", response_model=dict)
async def promote_tool_version(
    tool_id: str,
    version_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        tool = await ToolVersionManager(db).promote_version(
            tool_id=tool_id,
            version_id=version_id,
            user_id=current_user.id,
        )
    except VersionError as exc:
        if exc.code in {"TOOL_NOT_FOUND", "VERSION_NOT_FOUND", "VERSION_MISMATCH"}:
            raise NotFoundException("工具或工具版本不存在") from exc
        if exc.code == "SMOKE_REQUIRED":
            raise ValidationException("候选版本必须先通过成功的 smoke 验证") from exc
        raise ValidationException(exc.message) from exc

    return success_response(
        data={
            "tool_id": tool.id,
            "tool_version_id": version_id,
            "current_version_id": tool.current_version_id,
            "is_active": True,
        },
        message="工具版本已提升为当前版本",
    )
