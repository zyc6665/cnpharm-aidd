# backend/app/common/responses.py
"""统一响应格式"""

from typing import Any, Optional

from app.schemas.common import PaginatedResponse


def success_response(
    data: Any = None,
    message: str = "success",
    code: int = 200
) -> dict:
    """成功响应"""
    return {
        "code": code,
        "message": message,
        "data": data
    }


def paginated_response(
    *,
    items: list[Any],
    total: int,
    page: int,
    page_size: int,
    message: str = "success",
    code: int = 200,
) -> dict:
    """标准分页响应"""
    return success_response(
        data=PaginatedResponse.create(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        ).model_dump(),
        message=message,
        code=code,
    )


def error_response(
    message: str,
    code: int = 500,
    detail: Optional[Any] = None
) -> dict:
    """错误响应"""
    response = {
        "code": code,
        "message": message,
        "data": None
    }
    if detail:
        response["detail"] = detail
    return response
