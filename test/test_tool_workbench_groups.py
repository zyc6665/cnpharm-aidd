"""工具工作台分组测试。"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
SCRIPTS_ROOT = PROJECT_ROOT / "backend" / "scripts"
CREATE_SCRIPT = SCRIPTS_ROOT / "create_tool_workbench_groups.sql"
VERIFY_SCRIPT = SCRIPTS_ROOT / "verify_tool_workbench_groups.sql"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models import tools as tool_models
from app.schemas import tools as tool_schemas


def get_tool_workbench_group_model():
    """获取工作台分组模型。"""
    return getattr(tool_models, "ToolWorkbenchGroup", None)


def get_tool_workbench_group_mapping_model():
    """获取工作台分组映射模型。"""
    return getattr(tool_models, "ToolWorkbenchGroupMapping", None)


def read_script(path: Path) -> str:
    """读取 SQL 脚本文本。"""
    return path.read_text(encoding="utf-8")


def test_tool_workbench_group_model_exists():
    """存在独立的工具工作台分组模型。"""
    tool_workbench_group_model = get_tool_workbench_group_model()

    assert tool_workbench_group_model is not None, "缺少 ToolWorkbenchGroup 模型"


def test_tool_workbench_group_mapping_model_exists():
    """存在工具与工作台分组映射模型。"""
    tool_workbench_group_mapping_model = get_tool_workbench_group_mapping_model()

    assert tool_workbench_group_mapping_model is not None, "缺少 ToolWorkbenchGroupMapping 模型"


def test_tool_workbench_group_schemas_exist():
    """存在工作台分组相关 schema。"""
    assert getattr(tool_schemas, "ToolWorkbenchGroupCreate", None) is not None, (
        "缺少 ToolWorkbenchGroupCreate schema"
    )
    assert getattr(tool_schemas, "ToolWorkbenchGroupUpdate", None) is not None, (
        "缺少 ToolWorkbenchGroupUpdate schema"
    )
    assert getattr(tool_schemas, "ToolWorkbenchGroupResponse", None) is not None, (
        "缺少 ToolWorkbenchGroupResponse schema"
    )


def test_tool_workbench_group_mapping_schemas_exist():
    """存在工作台分组与工具映射相关 schema。"""
    assert getattr(tool_schemas, "ToolWorkbenchGroupMappingCreate", None) is not None, (
        "缺少 ToolWorkbenchGroupMappingCreate schema"
    )
    assert getattr(tool_schemas, "ToolWorkbenchGroupMappingResponse", None) is not None, (
        "缺少 ToolWorkbenchGroupMappingResponse schema"
    )


def test_tool_workbench_group_create_script_exists():
    """存在工作台分组建表脚本。"""
    assert CREATE_SCRIPT.exists(), f"缺少建表脚本: {CREATE_SCRIPT}"


def test_tool_workbench_group_verify_script_exists():
    """存在工作台分组校验脚本。"""
    assert VERIFY_SCRIPT.exists(), f"缺少校验脚本: {VERIFY_SCRIPT}"


def test_create_script_contains_required_tables_and_constraint():
    """建表脚本包含新表和唯一约束。"""
    sql = read_script(CREATE_SCRIPT)

    assert "BEGIN;" in sql
    assert "CREATE TABLE IF NOT EXISTS tool_workbench_groups" in sql
    assert "CREATE TABLE IF NOT EXISTS tool_workbench_group_mappings" in sql
    assert "UNIQUE (tool_id, group_id)" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_tool_workbench_group_mappings_tool_id" in sql
    assert "COMMIT;" in sql


def test_verify_script_contains_basic_checks():
    """校验脚本包含基础验证查询。"""
    sql = read_script(VERIFY_SCRIPT)

    assert "tool_workbench_group_count" in sql
    assert "tool_workbench_group_mapping_count" in sql
    assert "dangling_tool_workbench_group_refs" in sql
    assert "dangling_tool_refs" in sql
    assert "duplicate_tool_group_mappings" in sql
    assert "PRAGMA foreign_key_check" in sql
