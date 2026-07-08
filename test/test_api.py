"""API 入口核心回归测试。"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def read_backend_source(relative_path: str) -> str:
    """读取后端源码文件。"""
    return (BACKEND_ROOT / relative_path).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_system_health_shape():
    """健康检查应返回稳定的状态和版本字段。"""
    from app.main import health_check

    data = await health_check()

    assert data["status"] == "healthy"
    assert isinstance(data["version"], str)
    assert data["version"]


def test_enum_definitions():
    """核心枚举应保留当前持久化值。"""
    from app.models.files import FileSourceType
    from app.models.tasks import TaskStatus

    assert FileSourceType.UPLOAD.value == "upload"
    assert TaskStatus.FAILURE.value == "FAILURE"
    assert not hasattr(TaskStatus, "FAILED")


def test_file_model():
    """File 模型应使用 size_bytes 字段而不是旧 size 字段。"""
    from app.models.files import File as FileModel

    assert hasattr(FileModel, "size_bytes")
    assert not hasattr(FileModel, "size")


def test_database_schema():
    """本地开发数据库存在时，files 表应使用 size_bytes 字段。"""
    db_path = BACKEND_ROOT / "storage" / "scitool.db"
    if not db_path.exists():
        pytest.skip("本地数据库不存在，跳过 schema 验证")

    with sqlite3.connect(str(db_path)) as conn:
        columns = conn.execute("PRAGMA table_info(files)").fetchall()

    column_names = {column[1] for column in columns}
    assert "size_bytes" in column_names
    assert "size" not in column_names


def test_task_status_usage():
    """任务 API 应使用 TaskStatus.value，避免枚举对象直接入库。"""
    content = read_backend_source("app/api/v1/tasks.py")
    direct_enum_assignment = re.compile(r"status\s*=\s*TaskStatus\.")

    incorrect_usages = [
        (line_no, line.strip())
        for line_no, raw_line in enumerate(content.splitlines(), 1)
        for line in [raw_line.split("#", 1)[0]]
        if direct_enum_assignment.search(raw_line.split("#", 1)[0])
        and ".value" not in line
    ]

    assert incorrect_usages == []
    assert re.search(r"TaskStatus\.\w+\.value", content)
