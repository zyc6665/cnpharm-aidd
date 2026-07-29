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

    # Phase 3: admin/index.vue 改用数据驱动 v-for 循环 adminTabs 数组
    assert "key: 'tool-categories'" in admin_index_source
    assert "labelKey: 'admin.toolCategories'" in admin_index_source
    assert "navigate(tab.key)" in admin_index_source


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
    assert "normalizeCategorySlug" in page_source
    assert "formState.slug or formState.name" not in page_source
    assert "formState.slug || formState.name" in page_source


def test_admin_tool_forms_use_category_id_and_public_create_entry_is_removed():
    """管理员工具表单应使用分类接口和 category_id，普通用户入口应移除。"""
    admin_tools_source = read_source("frontend/src/views/admin/Tools.vue")
    create_source = read_source("frontend/src/views/tools/Create.vue")
    list_source = read_source("frontend/src/views/tools/List.vue")
    api_source = read_source("frontend/src/api/tools.ts")

    assert "adminGetToolCategories" in api_source

    # Phase 3: admin/Tools.vue 工具表单交棒给 Create.vue，使用 router.push 而非内联 createTool/updateTool
    assert "adminGetToolCategories" in admin_tools_source
    assert "openCreatePage" in admin_tools_source  # 跳转到 Create.vue
    assert "category_id" in admin_tools_source  # import 等流程仍使用 category_id

    assert "name=\"category_id\"" in create_source
    assert "formState.category_id" in create_source
    assert "category_id: formState.category_id" in create_source

    assert "goToCreate" not in list_source
    assert "name: 'ToolCreate'" not in read_source("frontend/src/router/index.ts")
    assert "selectedCategory" in list_source
    assert "category: selectedCategory.value" in list_source


def test_admin_tool_form_exposes_agent_capability_config():
    """管理员工具表单应暴露 Agent 动态注册配置，而不是只能手写隐藏 JSON。"""
    create_source = read_source("frontend/src/views/tools/Create.vue")

    assert "Agent 编排能力" in create_source
    assert "agent_capability_enabled" in create_source
    assert "agent_capability" in create_source
    assert "molecule_generation" in create_source
    assert "agent_inputs" in create_source
    assert "agent_outputs" in create_source
    assert "config.agent_capability" in create_source


def test_tool_form_uses_structured_executor_config_editors():
    """执行器常用映射和列表不应要求管理员手写 JSON。"""
    create_source = read_source("frontend/src/views/tools/Create.vue")

    assert "StructuredKeyValueEditor" in create_source
    assert "StructuredStringListEditor" in create_source
    assert "apiHeadersText" not in create_source
    assert "dockerEnvText" not in create_source
    assert "sshEnvText" not in create_source
    assert "sshOutputGlobsText" not in create_source
