# backend/app/api/v1/verification.py
"""验证码 API"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.schemas.verification import (
    SendCodeRequest,
    VerifyCodeRequest,
)
from app.services.verification.service import (
    get_verification_service,
    RateLimitError,
    DailyLimitError,
    InvalidCodeError
)
from app.common.responses import success_response
from app.common.exceptions import ValidationException, TooManyRequestsException

router = APIRouter()


@router.post("/send-code", response_model=dict)
async def send_verification_code(
    request: Request,
    data: SendCodeRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    发送验证码

    - **email**: 邮箱地址
    - **purpose**: 用途 (register: 注册, reset_password: 重置密码)

    限制：
    - 60 秒内不能重复发送
    - 每日最多发送 10 次
    """
    # 获取客户端 IP
    client_ip = request.client.host if request.client else None

    verification_service = await get_verification_service(db)

    try:
        success, expires_in = await verification_service.send_code(
            email=data.email,
            purpose=data.purpose,
            ip_address=client_ip
        )

        return success_response(
            data={
                "expires_in": expires_in
            },
            message="验证码已发送，请查收邮件"
        )

    except RateLimitError as e:
        raise TooManyRequestsException(str(e))

    except DailyLimitError as e:
        raise TooManyRequestsException(str(e))


@router.post("/verify", response_model=dict)
async def verify_code(
    data: VerifyCodeRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    验证验证码（预校验）

    用于前端在提交表单前验证验证码是否有效。
    注意：此接口不会消耗验证码，验证码仍可用于注册/重置密码。

    - **email**: 邮箱地址
    - **code**: 6 位验证码
    - **purpose**: 用途
    """
    verification_service = await get_verification_service(db)

    try:
        # 预校验不标记为已使用
        await verification_service.verify_code(
            email=data.email,
            code=data.code,
            purpose=data.purpose,
            mark_used=False
        )

        return success_response(
            data={"valid": True},
            message="验证码有效"
        )

    except InvalidCodeError as e:
        raise ValidationException(str(e))
