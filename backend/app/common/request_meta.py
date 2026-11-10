"""从请求里取审计需要的来源信息（客户端 IP、User-Agent）。

审计事件的两列 ``ip`` / ``user_agent`` 只服务一件事：**事后追查「是谁、从哪里」
做的这次操作**。因此这里只做取值，不做任何可信度加工——是否信任
``X-Forwarded-For`` 由部署侧的网关决定（见 ``docs/13`` 的反向代理约定），
应用层若自己解析转发头，反而会让任何人伪造审计来源。
"""

from __future__ import annotations

from typing import Optional

from fastapi import Request


def client_meta(request: Optional[Request]) -> tuple[Optional[str], Optional[str]]:
    """返回 ``(client_ip, user_agent)``；缺字段时对应项为 ``None``。"""
    if request is None:
        return None, None
    client = getattr(request, "client", None)
    ip = getattr(client, "host", None) if client else None
    headers = getattr(request, "headers", None)
    user_agent = headers.get("user-agent") if headers is not None else None
    return ip, user_agent


__all__ = ["client_meta"]
