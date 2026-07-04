"""通用响应工具测试。"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common.responses import paginated_response


def test_paginated_response_builds_standard_total_pages() -> None:
    """分页响应应统一生成 total_pages 字段。"""
    response = paginated_response(
        items=[{"id": "task-1"}],
        total=21,
        page=2,
        page_size=10,
    )

    assert response == {
        "code": 200,
        "message": "success",
        "data": {
            "items": [{"id": "task-1"}],
            "total": 21,
            "page": 2,
            "page_size": 10,
            "total_pages": 3,
        },
    }


def test_paginated_response_handles_empty_results() -> None:
    """空结果分页总页数应为 0。"""
    response = paginated_response(items=[], total=0, page=1, page_size=20)

    assert response["data"]["total_pages"] == 0
