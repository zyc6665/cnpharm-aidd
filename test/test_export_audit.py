"""导出留痕的单元级守护（V3.0 §6.2「导出下载留痕」/ docs/26 H-9）。

端到端覆盖在各自的接口测试里（``test_traceability_api``、``test_result_report_pdf``、
``test_compounds_api``、``test_targets_api``）；这里补两件端到端测不出来的事：

1. 审计写失败**不能**把一次已经生成好的导出变成 500；
2. 每个 ``:export`` 端点都必须真的调用 ``record_export``——否则将来新增导出接口
   时，审计会悄悄少一条，而「查不到」本身没有任何报错。
"""

from __future__ import annotations

import ast
import sys
from types import SimpleNamespace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.logging.audit import ResourceType, get_audit_logger  # noqa: E402
from app.services.audit_exports import record_export  # noqa: E402

API_DIR = BACKEND_ROOT / "app" / "api" / "v1"


def _export_route_functions() -> list[tuple[str, str, ast.AsyncFunctionDef]]:
    """返回 ``[(模块名, 路由路径, 函数)]``，只取路径里带 ``:export`` 的端点。"""
    found: list[tuple[str, str, ast.AsyncFunctionDef]] = []
    for path in sorted(API_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                route = _route_path(decorator)
                if route and ":export" in route:
                    found.append((path.name, route, node))
    return found


def _route_path(decorator: ast.expr) -> str | None:
    if not isinstance(decorator, ast.Call) or not decorator.args:
        return None
    first = decorator.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def test_every_export_route_records_an_audit_event() -> None:
    routes = _export_route_functions()
    assert len(routes) >= 4, f"导出端点变少了？实际找到 {len(routes)} 个"

    missing = []
    for module, route, node in routes:
        source = ast.get_source_segment(
            (API_DIR / module).read_text(encoding="utf-8"), node
        ) or ""
        if "record_export(" not in source:
            missing.append(f"{module}::{node.name} ({route})")
    assert not missing, f"以下导出端点没有留痕：{missing}"


def test_record_export_does_not_raise_when_audit_fails(monkeypatch) -> None:
    """审计是旁路：留痕失败只能打日志，不能把导出变成 500。"""

    def _explode(event) -> None:
        raise RuntimeError("audit sink down")

    audit_logger = get_audit_logger()
    monkeypatch.setattr(audit_logger, "enable_file_logging", False)
    monkeypatch.setattr(audit_logger, "enable_db_logging", True)
    monkeypatch.setattr(audit_logger, "_db_writer", _explode)

    record_export(
        request=None,
        current_user=SimpleNamespace(id="user-1"),
        resource_type=ResourceType.TASK,
        resource_id="task-1",
        resource_name="demo",
        kind="traceability_package",
    )


def test_record_export_tolerates_a_missing_request() -> None:
    """后台任务/测试里没有 Request 时也不能炸（来源信息缺省为 None）。"""
    events: list = []
    audit_logger = get_audit_logger()
    original_writer = audit_logger._db_writer
    original_file = audit_logger.enable_file_logging
    original_db = audit_logger.enable_db_logging
    try:
        audit_logger.enable_file_logging = False
        audit_logger.enable_db_logging = True
        audit_logger._db_writer = events.append
        record_export(
            request=None,
            current_user=SimpleNamespace(id="user-2"),
            resource_type=ResourceType.STRUCTURE,
            resource_id="structure-1",
        )
    finally:
        audit_logger._db_writer = original_writer
        audit_logger.enable_file_logging = original_file
        audit_logger.enable_db_logging = original_db

    assert len(events) == 1
    assert events[0].client_ip is None
    assert events[0].user_agent is None
