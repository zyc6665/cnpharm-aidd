"""管理员工具分类前端表面测试。"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path: str) -> str:
    """读取源码文件。"""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_admin_tool_categories_route_and_entry_exist():
    """管理后台应存在分类管理路由和侧边栏入口。"""
    router_source = read_source("frontend/src/router/index.ts")
    admin_index_source = read_source("frontend/src/views/admin/index.vue")

    assert "path: 'tool-categories'" in router_source
    assert "name: 'AdminToolCategories'" in router_source
    assert "ToolCategories.vue" in router_source

    assert "key=\"tool-categories\"" in admin_index_source
    assert "navigate('tool-categories')" in admin_index_source
    assert "t('admin.toolCategories')" in admin_index_source


def test_admin_tool_categories_page_has_management_actions():
    """分类管理页应提供增删改查、启停和排序入口。"""
    page_source = read_source("frontend/src/views/admin/ToolCategories.vue")

    assert "showCreateModal" in page_source
    assert "handleEdit" in page_source
    assert "handleToggleStatus" in page_source
    assert "handleDelete" in page_source
    assert "moveCategory" in page_source
    assert "ArrowUpOutlined" in page_source
    assert "ArrowDownOutlined" in page_source


def test_admin_tool_forms_use_category_id_and_public_create_entry_is_removed():
    """管理员工具表单应使用分类接口和 category_id，普通用户入口应移除。"""
    admin_tools_source = read_source("frontend/src/views/admin/Tools.vue")
    create_source = read_source("frontend/src/views/tools/Create.vue")
    list_source = read_source("frontend/src/views/tools/List.vue")
    api_source = read_source("frontend/src/api/tools.ts")

    assert "adminGetToolCategories" in api_source

    assert "toolForm.category_id" in admin_tools_source
    assert "adminGetToolCategories" in admin_tools_source
    assert "createTool(" in admin_tools_source
    assert "updateTool(" in admin_tools_source
    assert "category_id:" in admin_tools_source

    assert "name=\"category_id\"" in create_source
    assert "formState.category_id" in create_source
    assert "category_id: formState.category_id" in create_source

    assert "goToCreate" not in list_source
    assert "name: 'ToolCreate'" not in read_source("frontend/src/router/index.ts")
    assert "selectedCategory" in list_source
    assert "category: selectedCategory.value" in list_source
