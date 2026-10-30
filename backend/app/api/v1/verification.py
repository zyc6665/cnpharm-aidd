# backend/app/api/v1/verification.py
"""验证码 API（邮箱自助链路已停用）。

企业内网改为 LDAP 认证后不再走邮箱验证码：``send-code`` / ``verify`` 保留路由
（前端/旧客户端仍可能调用）但首行直接返回 HTTP 403 + 业务码 40002。
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.schemas.verification import (
    SendCodeRequest,
    VerifyCodeRequest,
)
from app.common.exceptions import BusinessException

router = APIRouter()
_DISABLED_MESSAGE = "该功能已停用，请联系管理员"


@router.post("/send-code", response_model=dict)
async def send_verification_code(
    request: Request,
    data: SendCodeRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """发送验证码（已停用）。"""
    raise BusinessException(_DISABLED_MESSAGE, http_status=403, code=40002)


@router.post("/verify", response_model=dict)
async def verify_code(
    data: VerifyCodeRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """验证验证码（已停用）。"""
    raise BusinessException(_DISABLED_MESSAGE, http_status=403, code=40002)
