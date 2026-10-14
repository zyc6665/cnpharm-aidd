"""Admin APIs for static tool templates."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from app.auth.dependencies import get_admin_user
from app.models.users import User


router = APIRouter()


@router.get("", response_model=dict)
async def list_tool_templates(
    current_user: User = Depends(get_admin_user),
) -> dict:
    raise HTTPException(
        status_code=410,
        detail="旧工具模板注册入口已下线，请使用管理员 Tool Package 注册流程",
    )


@router.post("/{template_key}/draft", response_model=dict)
async def create_tool_draft_from_template(
    template_key: str,
    current_user: User = Depends(get_admin_user),
) -> dict:
    raise HTTPException(
        status_code=410,
        detail="旧工具模板注册入口已下线，请使用管理员 Tool Package 注册流程",
    )
