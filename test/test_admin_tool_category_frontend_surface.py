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

    # admin/index.vue 使用分组数据驱动 v-for 渲染侧边栏
    assert "key: 'tool-categories'" in admin_index_source
    assert "labelKey: 'admin.toolCategories'" in admin_index_source
    assert 'navigate(item)' in admin_index_source


def test_admin_tool_categories_page_is_read_only_capability_families():
    """分类页只读展示由模型能力族自动派生的分类，不再提供手工维护入口。"""
    page_source = read_source("frontend/src/views/admin/ToolCategories.vue")

    assert "admin.toolCategoriesAutoTitle" in page_source
    assert "admin.toolCategoriesAutoHint" in page_source
    assert "modelFamilyLabelKey" in page_source
    assert "adminGetToolCategories" in page_source
    assert "record.tool_count" in page_source
    assert "showCreateModal" not in page_source
    assert "handleEdit" not in page_source
    assert "handleDelete" not in page_source
    assert "moveCategory" not in page_source


def test_admin_tool_registration_uses_tool_packages_only():
    """管理员工具页只保留 Tool Package 注册入口，不暴露旧创建/导入入口。"""
    admin_tools_source = read_source("frontend/src/views/admin/Tools.vue")
    list_source = read_source("frontend/src/views/tools/List.vue")
    api_source = read_source("frontend/src/api/tools.ts")
    router_source = read_source("frontend/src/router/index.ts")

    assert "adminGetToolCategories" in api_source
    assert "openToolPackages" in admin_tools_source
    assert "openCreatePage" not in admin_tools_source
    assert "importToolConfig" not in admin_tools_source
    assert "path: 'tools/create'" not in router_source

    assert "goToCreate" not in list_source
    assert "name: 'ToolCreate'" not in read_source("frontend/src/router/index.ts")
    assert "selectedCategory" in list_source
    assert "category: selectedCategory.value" in list_source


def test_admin_tool_form_is_k8s_only_and_links_to_package_registration():
    """工具编辑页固定 k8s_job 执行，并引导到模型交付包完成注册。"""
    create_source = read_source("frontend/src/views/tools/Create.vue")

    assert "模型接入教程" in create_source
    assert "goGuide" in create_source
    assert "/admin/model-guide" in create_source
    assert "k8s_job" in create_source
    assert "k8s_image" in create_source
    assert "k8s_resource_profile" in create_source
    assert "Agent 编排能力" not in create_source
    # 旧版 Agent 能力不再由管理员编辑；加载旧工具时仅静默关闭兼容字段。
    assert "agent_capability_enabled = false" in create_source


def test_tool_form_uses_structured_k8s_runtime_editors():
    """工具编辑页只维护 k8s 镜像与资源画像，不再暴露执行器 JSON。"""
    create_source = read_source("frontend/src/views/tools/Create.vue")

    assert "镜像 digest" in create_source
    assert "资源画像" in create_source
    assert "k8s_image" in create_source
    assert "k8s_resource_profile" in create_source
    assert "apiHeadersText" not in create_source
    assert "dockerEnvText" not in create_source
    assert "sshEnvText" not in create_source
    assert "sshOutputGlobsText" not in create_source


def test_legacy_tool_template_registration_page_is_not_routable():
    """旧模板注册能力不再通过管理员创建路由暴露。"""
    router_source = read_source("frontend/src/router/index.ts")

    assert "path: 'tools/create'" not in router_source
    assert "name: 'AdminToolCreate'" not in router_source
