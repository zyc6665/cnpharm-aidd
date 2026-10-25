"""Administrator audit log query API (docs/05 §11, docs/06 P-38).

The audit trail has two destinations (see ``app.services.audit_sink``): a rotating
JSON file that survives database outages, and the ``audit_logs`` table that this
endpoint reads. Only administrators may query it — the trail names who did what,
so read access is itself a privileged operation and is recorded.

Filters follow the columns the table actually has (actor / action / result /
resource / time range) rather than a free-text search: an auditor arriving with a
ticket number needs deterministic, index-backed lookups, not fuzzy matching.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_admin_user
from app.common.exceptions import ValidationException
from app.common.responses import paginated_response, success_response
from app.database.session import get_db
from app.logging.audit import AuditAction, ResourceType, get_audit_logger
from app.models.traceability import AuditLog
from app.models.users import User

router = APIRouter()

__all__ = ["router"]

#: Guard rails for the external filter surface. Unknown values are rejected rather
#: than silently ignored — an auditor must never believe they filtered when they did not.
MAX_PAGE_SIZE = 200

#: 入库值是大写枚举（见 ``app.services.audit_sink.event_to_row``）。校验用大写集合，
#: 但查询时把调用方传入的小写也归一化，避免审计员按文档抄 ``login`` 却被 422 挡住。
_AUDIT_ACTIONS = {item.value.upper() for item in AuditAction}
_RESOURCE_TYPES = {item.value.upper() for item in ResourceType}
_RESULT_VALUES = {"SUCCESS", "FAILURE", "DENIED", "ERROR"}


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def serialize_audit_log(row: AuditLog) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "actor": row.actor,
        "actor_id": row.actor_id,
        "action": row.action,
        "result": row.result,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "resource_name": row.resource_name,
        "detail": row.detail or {},
        "ip": row.ip,
        "user_agent": row.user_agent,
        "request_id": row.request_id,
        "created_at": _iso(row.created_at),
    }


@router.get("", summary="审计日志查询")
async def list_audit_logs(
    actor: str | None = Query(default=None, description="操作者用户名（精确匹配）"),
    action: str | None = Query(default=None, description="动作，见 AuditAction"),
    result: str | None = Query(default=None, description="success/failure/denied/error"),
    resource_type: str | None = Query(default=None, description="资源类型，见 ResourceType"),
    resource_id: str | None = Query(default=None, description="资源 ID（精确匹配）"),
    request_id: str | None = Query(default=None, description="请求 ID（精确匹配）"),
    start_time: datetime | None = Query(default=None, description="起始时间（含）"),
    end_time: datetime | None = Query(default=None, description="结束时间（含）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Page through the audit trail with index-backed filters."""
    action = action.upper() if action else None
    resource_type = resource_type.upper() if resource_type else None
    result = result.upper() if result else None
    if action and action not in _AUDIT_ACTIONS:
        raise ValidationException(f"不支持的审计动作: {action}")
    if resource_type and resource_type not in _RESOURCE_TYPES:
        raise ValidationException(f"不支持的资源类型: {resource_type}")
    if result and result not in _RESULT_VALUES:
        raise ValidationException(f"不支持的审计结果: {result}")
    if start_time and end_time and start_time > end_time:
        raise ValidationException("起始时间不能晚于结束时间")

    query = select(AuditLog)
    if actor:
        query = query.where(AuditLog.actor == actor)
    if action:
        query = query.where(AuditLog.action == action)
    if result:
        query = query.where(AuditLog.result == result)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if resource_id:
        query = query.where(AuditLog.resource_id == resource_id)
    if request_id:
        query = query.where(AuditLog.request_id == request_id)
    if start_time:
        query = query.where(AuditLog.created_at >= start_time)
    if end_time:
        query = query.where(AuditLog.created_at <= end_time)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (
        await db.execute(
            query.order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    # Reading the trail is itself an auditable action (docs/10 AUD-06 adjacent):
    # the file trail records it without needing this request's transaction to commit.
    get_audit_logger().log_data_access(
        user_id=str(current_user.id),
        resource_type=ResourceType.SYSTEM,
        resource_id="audit_logs",
        action=AuditAction.READ,
        reason="查询审计日志",
        user_email=current_user.email,
    )

    return paginated_response(
        items=[serialize_audit_log(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/facets", summary="审计日志过滤取值")
async def get_audit_facets(
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Distinct actors/actions present in the trail, so the console can offer real options."""
    actors = (
        await db.execute(select(AuditLog.actor).distinct().order_by(AuditLog.actor))
    ).scalars().all()
    actions = (
        await db.execute(select(AuditLog.action).distinct().order_by(AuditLog.action))
    ).scalars().all()
    return success_response(
        data={
            "actors": [value for value in actors if value],
            "actions": [value for value in actions if value],
            "resultValues": sorted(_RESULT_VALUES),
            "resourceTypes": sorted(_RESOURCE_TYPES),
        }
    )
