"""研发阶段与决策记录 API（docs/05 §3.2、§3.3；docs/03 §3.6）。

端点挂在 ``project_router`` 上（无 prefix，由 ``api_router`` 统一挂 ``/projects``，
与 targets / compounds / results 一致）。本模块只有三级路径，没有项目外的独立
路径，所以不额外导出 ``router``。

阶段接口是**纯推导**（``app.services.project_stage``），决策写入走
``app.services.decisions``。本模块只负责 HTTP 语义、权限入口与响应包装。

响应字段命名：阶段对象按 ``docs/05`` §3.2 用 camelCase（``currentStage`` 等），决策
对象用 snake_case（与 ``serialize_candidate`` 等既有序列化一致）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.exceptions import ValidationException
from app.common.responses import paginated_response, success_response
from app.database.session import get_db
from app.feature_flags import require_feature_flag
from app.models.decisions import DECISION_POINTS
from app.models.users import User
from app.schemas.decisions import DecisionCreate
from app.services.decisions import (
    DECISION_READ_ROLES,
    create_decision,
    list_decisions,
    serialize_decision,
)
from app.services.project_access import require_project_role
from app.services.project_stage import compute_project_stage

_FEATURE_FLAG = Depends(require_feature_flag("AIDD_PROJECT_WORKSPACE_ENABLED"))

project_router = APIRouter(dependencies=[_FEATURE_FLAG])

__all__ = ["project_router"]


#: 阶段响应的字段名按 ``docs/05`` §3.2 的 camelCase 输出；Service 内部一律 snake_case。
STAGE_FIELD_NAMES = {
    "current_stage": "currentStage",
    "stage_name": "stageName",
    "reached_stages": "reachedStages",
    "next_stage": "nextStage",
}


def _stage_payload(stage: dict) -> dict:
    return {STAGE_FIELD_NAMES.get(key, key): value for key, value in stage.items()}


@project_router.get("/{project_id}/stage", response_model=dict)
async def get_project_stage(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """当前研发阶段与缺口提示（只读，不落库，允许回退）。"""
    await require_project_role(
        db,
        project_id=project_id,
        user=current_user,
        allowed_roles=DECISION_READ_ROLES,
    )
    stage = await compute_project_stage(db, project_id=project_id)
    return success_response(data=_stage_payload(stage))


@project_router.get("/{project_id}/decisions", response_model=dict)
async def list_project_decisions(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    decision_point: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """决策记录列表，按决策时间倒序分页。"""
    await require_project_role(
        db,
        project_id=project_id,
        user=current_user,
        allowed_roles=DECISION_READ_ROLES,
    )
    if decision_point is not None and decision_point not in DECISION_POINTS:
        # 静默忽略会让调用方以为筛选生效了，却拿到全量数据。
        raise ValidationException(
            f"decision_point 必须是 {'、'.join(DECISION_POINTS)} 之一",
            detail={"value": decision_point},
        )

    rows, total = await list_decisions(
        db,
        project_id=project_id,
        page=page,
        page_size=page_size,
        decision_point=decision_point,
    )
    return paginated_response(
        items=[serialize_decision(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@project_router.post("/{project_id}/decisions", response_model=dict)
async def create_project_decision(
    project_id: str,
    payload: DecisionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """提交一次研发决策（只追加；写入同时追加审计事件）。"""
    record = await create_decision(
        db, project_id=project_id, user=current_user, data=payload
    )
    return success_response(data=serialize_decision(record))
