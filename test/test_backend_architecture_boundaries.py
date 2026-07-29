"""后端架构边界测试。"""

from __future__ import annotations

import ast
from pathlib import Path


BACKEND_APP = Path("backend/app")
API_COMPOSITION_ROOTS = {Path("main")}
API_ROUTE_ROOT = BACKEND_APP / "api" / "v1"
TOOL_ROUTE_MODULES = {
    "tool_route_utils.py",
    "tool_versions.py",
    "tools_admin.py",
    "tools_public.py",
}


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


def test_tool_routes_have_dedicated_modules() -> None:
    """工具公开、管理、版本与共享逻辑应拥有独立模块。"""
    existing_modules = {path.name for path in API_ROUTE_ROOT.glob("*.py")}

    assert TOOL_ROUTE_MODULES <= existing_modules


def test_public_tool_router_owns_public_and_user_routes() -> None:
    """公开工具路由应覆盖既有查询、示例、契约与收藏入口。"""
    from app.api.v1.tools_public import router

    route_keys = {
        (method, route.path)
        for route in router.routes
        for method in getattr(route, "methods", set())
    }
    expected_routes = {
        ("GET", ""),
        ("GET", "/workbench-groups"),
        ("GET", "/categories"),
        ("GET", "/tags"),
        ("GET", "/{tool_id}/example"),
        ("POST", "/{tool_id}/example/apply"),
        ("GET", "/{tool_id}/contract"),
        ("GET", "/{tool_id}/example/files/{field}/preview"),
        ("GET", "/{tool_id}"),
        ("POST", "/{tool_id}/favorite"),
        ("DELETE", "/{tool_id}/favorite"),
    }

    assert expected_routes <= route_keys


class _UsedNames(ast.NodeVisitor):
    """收集模块中实际引用的本地名称。"""

    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        return

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        return

    def visit_Name(self, node: ast.Name) -> None:
        self.names.add(node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.visit(node.value)


def _imported_names(tree: ast.AST) -> list[tuple[str, int, str]]:
    """返回导入的本地名称、行号和描述。"""
    imports: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue
            module = node.module or ""
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".")[0]
                imports.append((local_name, node.lineno, f"from {module} import {alias.name}"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".")[0]
                imports.append((local_name, node.lineno, f"import {alias.name}"))
    return imports


def test_api_route_modules_do_not_keep_unused_imports() -> None:
    """API 路由模块不应保留未使用导入。"""
    offenders: list[str] = []

    for source_path in sorted(API_ROUTE_ROOT.glob("*.py")):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        used_names = _UsedNames()
        used_names.visit(tree)

        for local_name, line_no, import_text in _imported_names(tree):
            if local_name not in used_names.names:
                offenders.append(f"{source_path}:{line_no} unused {import_text}")

    assert offenders == []
