"""代码修复静态回归测试。"""

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


def test_file_source_type_enum():
    """FileSourceType 应包含上传来源枚举。"""
    from app.models.files import FileSourceType

    assert FileSourceType.UPLOAD.value == "upload"


def test_file_model_field():
    """File 模型应使用 size_bytes 字段而不是旧 size 字段。"""
    content = read_backend_source("app/models/files.py")

    assert "size_bytes = Column" in content
    assert "size = Column" not in content


def test_task_status_enum():
    """TaskStatus 应使用 FAILURE 而不是旧 FAILED。"""
    from app.models.tasks import TaskStatus

    assert TaskStatus.FAILURE.value == "FAILURE"
    assert not hasattr(TaskStatus, "FAILED")


def test_task_status_usage():
    """任务 API 和监控规则应使用稳定的 TaskStatus.value。"""
    tasks_api = read_backend_source("app/api/v1/tasks.py")
    alert_rules = read_backend_source("app/monitoring/alert_rules.py")

    assert re.search(r"TaskStatus\.\w+\.value", tasks_api)
    assert "TaskStatus.FAILED" not in alert_rules
    assert "TaskStatus.FAILURE.value" in alert_rules


def test_executor_implementation():
    """执行器关键文件处理方法不应退化为占位实现。"""
    content = read_backend_source("app/tasks/executor.py")
    required_methods = {
        "_prepare_input_files": "shutil.copy2",
        "_collect_output_files": "FileModel",
        "_process_output_files": "httpx.AsyncClient",
    }

    for method_name, expected_keyword in required_methods.items():
        pattern = rf"async def {method_name}\(.*?\):(.*?)(?=\n    async def |\n    def |\nclass |\Z)"
        match = re.search(pattern, content, re.DOTALL)
        assert match is not None, f"缺少执行器方法: {method_name}"
        method_body = match.group(1)
        assert not ("pass" in method_body and len(method_body.strip()) < 50)
        assert expected_keyword in method_body


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
