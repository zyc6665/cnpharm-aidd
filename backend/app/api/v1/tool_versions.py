"""工具版本管理路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_admin_user
from app.common.exceptions import ConflictException, NotFoundException
from app.common.responses import success_response
from app.database.session import get_db
from app.models.tools import Tool, ToolVersion
from app.models.users import User
from app.schemas.tools import ToolVersionCreate, ToolVersionResponse

router = APIRouter()


@router.get("/{tool_id}/versions", response_model=dict)
async def list_tool_versions(tool_id: str, db: AsyncSession = Depends(get_db)):
    versions = (
        await db.execute(
            select(ToolVersion)
            .where(ToolVersion.tool_id == tool_id)
            .order_by(ToolVersion.created_at.desc())
        )
    ).scalars().all()
    return success_response(
        data=[ToolVersionResponse.model_validate(version).model_dump() for version in versions]
    )


@router.post("/{tool_id}/versions", response_model=dict)
async def create_tool_version(
    tool_id: str,
    version_data: ToolVersionCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    tool = (
        await db.execute(select(Tool).where(Tool.id == tool_id))
    ).scalar_one_or_none()
    if not tool:
        raise NotFoundException("工具不存在")
    existing = await db.execute(
        select(ToolVersion).where(
            ToolVersion.tool_id == tool_id,
            ToolVersion.version == version_data.version,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictException("版本号已存在")
    version = ToolVersion(
        tool_id=tool_id,
        version=version_data.version,
        changelog=version_data.changelog,
        notes=version_data.notes,
        config=version_data.config,
        is_active=version_data.is_active,
    )
    db.add(version)
    await db.flush()
    if version_data.is_active:
        tool.current_version_id = version.id
    await db.commit()
    await db.refresh(version)
    return success_response(
        data=ToolVersionResponse.model_validate(version).model_dump(),
        message="版本创建成功",
    )
