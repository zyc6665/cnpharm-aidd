"""导出留痕（V3.0 §6.2「导出下载留痕」，`docs/26` H-9）。

**为什么单独一层**：``AuditAction.EXPORT`` 从建模之初就在枚举里，但全仓没有
一个调用方——审计表能查到「谁登录了」「谁下了哪个文件」，却查不到「谁把候选集
导成了 CSV」「谁导出了追溯包」。缺这一条，甲方按资源维度排查时就断在最后一步。

**为什么不做在下载端点**：导出接口返回的是「刚生成的文件 + 下载地址」，真正
取字节的动作发生在之后的文件下载接口（那里已有 ``FILE_DOWNLOAD``）。若只记
下载，就只能看见「某人下了个 json」，看不见导出范围与行数。所以这里记的是
**导出动作本身**，``resource_type`` / ``resource_id`` 指向被导出的领域对象。

**为什么吞掉异常**：审计是旁路。留痕失败不能把一次已经生成好的导出变成 500
（用户会重试，然后产生第二份文件）。失败打 warning，由监控发现。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import Request

from app.common.request_meta import client_meta
from app.logging.audit import ResourceType, get_audit_logger
from app.models.users import User

logger = logging.getLogger(__name__)


def record_export(
    *,
    request: Optional[Request],
    current_user: User,
    resource_type: ResourceType,
    resource_id: str,
    resource_name: Optional[str] = None,
    **detail: Any,
) -> None:
    """记录一次导出。``detail`` 里的键值会进审计详情的 ``detail`` 列。"""
    client_ip, user_agent = client_meta(request)
    try:
        get_audit_logger().log_export_operation(
            user_id=str(current_user.id),
            resource_type=resource_type,
            resource_id=str(resource_id),
            resource_name=resource_name,
            client_ip=client_ip,
            user_agent=user_agent,
            **detail,
        )
    except Exception:  # pragma: no cover - 防御性：审计不能阻断导出
        logger.warning("记录导出审计失败：resource=%s/%s", resource_type, resource_id)


__all__ = ["record_export"]
