"""核心修复回归测试。"""

from __future__ import annotations

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


def test_file_source_type_upload_enum_exists():
    """FileSourceType.UPLOAD 应保持为 upload。"""
    from app.models.files import FileSourceType

    assert FileSourceType.UPLOAD.value == "upload"


def test_file_model_uses_size_bytes_field():
    """File 模型应暴露 size_bytes 字段并移除旧 size 字段。"""
    from app.models.files import File as FileModel

    assert hasattr(FileModel, "size_bytes")
    assert not hasattr(FileModel, "size")


def test_file_model_can_create_upload_record():
    """File 模型应能用 size_bytes 和 upload 来源构造记录。"""
    from app.models.files import File as FileModel, FileSourceType

    file_record = FileModel(
        filename="test.txt",
        content_type="text/plain",
        size_bytes=1024,
        sha256="test123",
        source_type=FileSourceType.UPLOAD.value,
        storage_backend="local",
        storage_path="/tmp/test.txt",
    )

    assert file_record.size_bytes == 1024
    assert file_record.source_type == "upload"


def test_task_status_uses_failure_enum():
    """TaskStatus 应使用 FAILURE 而不是旧 FAILED。"""
    from app.models.tasks import TaskStatus

    assert TaskStatus.PENDING.value == "PENDING"
    assert TaskStatus.FAILURE.value == "FAILURE"
    assert not hasattr(TaskStatus, "FAILED")


def test_local_database_schema_uses_size_bytes_when_present():
    """本地开发数据库存在时，files 表应使用 size_bytes 字段。"""
    db_path = BACKEND_ROOT / "storage" / "scitool.db"
    if not db_path.exists():
        pytest.skip("本地数据库不存在，跳过 schema 验证")

    with sqlite3.connect(str(db_path)) as conn:
        columns = conn.execute("PRAGMA table_info(files)").fetchall()

    column_names = {column[1] for column in columns}
    assert "size_bytes" in column_names
    assert "size" not in column_names


def test_executor_file_handling_entrypoints_exist():
    """执行器应保留关键文件处理入口。"""
    executor_source = read_backend_source("app/tasks/executor.py")
    base_source = read_backend_source("app/tasks/executors/base.py")
    remote_api_source = read_backend_source("app/tasks/executors/remote_api.py")

    assert "class DockerExecutor" in executor_source
    assert "class RemoteAPIExecutor" in remote_api_source
    assert "async def _prepare_input_files" in executor_source
    assert "async def _collect_output_files" in base_source
    assert "async def _process_output_files" in remote_api_source
