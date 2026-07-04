"""后端架构边界测试。"""

from __future__ import annotations

import ast
from pathlib import Path


BACKEND_APP = Path("backend/app")
API_COMPOSITION_ROOTS = {Path("main")}


def _python_source_files() -> list[Path]:
    """返回 backend/app 下的生产 Python 源文件。"""
    return sorted(
        path
        for path in BACKEND_APP.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def test_backend_non_api_modules_do_not_import_api_routes() -> None:
    """非 API 层模块不应反向依赖 app.api.v1 路由模块。"""
    offenders: list[str] = []

    for source_path in _python_source_files():
        module_path = source_path.relative_to(BACKEND_APP).with_suffix("")
        if module_path.parts[:2] == ("api", "v1") or module_path in API_COMPOSITION_ROOTS:
            continue

        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("app.api.v1"):
                    offenders.append(f"{source_path}:{node.lineno} imports {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("app.api.v1"):
                        offenders.append(f"{source_path}:{node.lineno} imports {alias.name}")

    assert offenders == []
