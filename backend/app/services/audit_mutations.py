"""领域对象增删改的审计留痕（`docs/26` §7「靶点只能建不能删」的配套补齐）。

**为什么单独一层**：``AuditLogger.log_user_action`` 的签名里没有
``resource_name``，走它会写出 ``resource_name=NULL`` 的行。删除类操作恰恰最需要
名字快照——靶点被删之后 ``targets`` 表里已经没有那行可 join，只剩审计表上的
``resource_id`` 是认不出来的 UUID，「谁把 EGFR 删了」就查不出来。所以这里直接构造
``AuditEvent``，把名字写进列而不是 detail。

**为什么吞掉异常**：审计是旁路（docs/04 §3.2.2 最终一致）。删都删完了，再因为写
审计失败返回 500，用户只会重试一次并得到 404。失败打 warning，由监控发现。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import Request

from app.common.request_meta import client_meta
from app.logging.audit import (
    AuditAction,
    AuditEvent,
    AuditResult,
    ResourceType,
    get_audit_logger,
)
from app.models.users import User

logger = logging.getLogger(__name__)


def record_domain_action(
    *,
    action: AuditAction,
    request: Optional[Request],
    current_user: User,
    resource_type: ResourceType,
    resource_id: str,
    resource_name: Optional[str] = None,
    result: AuditResult = AuditResult.SUCCESS,
    **detail: Any,
) -> None:
    """记录一次领域对象状态变更（删除、归档等）。``detail`` 进审计详情的 ``detail`` 列。"""
    client_ip, user_agent = client_meta(request)
    try:
        get_audit_logger().log(
            AuditEvent(
                action=action,
                result=result,
                user_id=str(current_user.id),
                user_email=getattr(current_user, "email", None),
                resource_type=resource_type,
                resource_id=str(resource_id),
                resource_name=resource_name,
                client_ip=client_ip,
                user_agent=user_agent,
                extra=detail,
            )
        )
    except Exception:  # pragma: no cover - 防御性：审计不能阻断业务动作
        logger.warning(
            "记录领域对象审计失败：action=%s resource=%s/%s", action, resource_type, resource_id
        )


def record_domain_delete(
    *,
    request: Optional[Request],
    current_user: User,
    resource_type: ResourceType,
    resource_id: str,
    resource_name: Optional[str] = None,
    result: AuditResult = AuditResult.SUCCESS,
    **detail: Any,
) -> None:
    """记录一次领域对象删除（``record_domain_action`` 的 ``DELETE`` 快捷方式）。"""
    record_domain_action(
        action=AuditAction.DELETE,
        request=request,
        current_user=current_user,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        result=result,
        **detail,
    )


__all__ = ["record_domain_action", "record_domain_delete"]
