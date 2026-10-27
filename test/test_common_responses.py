"""通用响应工具测试。"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common.responses import paginated_response
from app.schemas.common import PaginatedResponse


def test_common_package_exports_paginated_response() -> None:
    """app.common 应导出统一分页响应 helper。"""
    from app.common import paginated_response as exported_paginated_response

    assert exported_paginated_response is paginated_response


def test_paginated_response_builds_standard_total_pages() -> None:
    """分页响应应统一生成 total_pages 字段。

    docs/05 §1.2 的统一响应体还要求 ``requestId`` / ``timestamp``（G-7 全链路串联），
    所以这条精确相等断言一并覆盖它们。``requestId`` 取当前请求的 trace_id：
    单元测试里没有请求上下文，因此是 ``None``。
    """
    response = paginated_response(
        items=[{"id": "task-1"}],
        total=21,
        page=2,
        page_size=10,
    )

    timestamp = response.pop("timestamp")
    assert response == {
        "code": 200,
        "message": "success",
        "requestId": None,
        "data": {
            "items": [{"id": "task-1"}],
            "total": 21,
            "page": 2,
            "page_size": 10,
            "total_pages": 3,
        },
    }
    # timestamp 必须是 docs/05 §1.2 示例里的带 Z 的 UTC ISO 字符串。
    assert isinstance(timestamp, str) and timestamp.endswith("Z")


def test_paginated_response_handles_empty_results() -> None:
    """空结果分页总页数应为 0。"""
    response = paginated_response(items=[], total=0, page=1, page_size=20)

    assert response["data"]["total_pages"] == 0


def test_paginated_schema_uses_total_pages_field() -> None:
    """分页 schema 字段名应与 API 响应保持一致。"""
    payload = PaginatedResponse.create(
        items=[{"id": "item-1"}],
        total=21,
        page=2,
        page_size=10,
    ).model_dump()

    assert payload["total_pages"] == 3
    assert "pages" not in payload
