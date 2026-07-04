# backend/app/common/responses.py
"""统一响应格式"""

from typing import Any, Optional
from app.schemas.common import BaseResponse


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
    total_pages = (total + page_size - 1) // page_size if total and page_size > 0 else 0
    return success_response(
        data={
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        },
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
