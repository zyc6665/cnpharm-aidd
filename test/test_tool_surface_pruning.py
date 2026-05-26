"""工具表面裁剪静态测试。"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path: str) -> str:
    """读取源码文件。"""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_backend_tool_review_and_user_tool_routes_are_removed():
    """后端不应再保留用户工具与审核流接口。"""
    api_source = read_source("backend/app/api/v1/tools.py")
    schema_source = read_source("backend/app/schemas/tools.py")

    assert "async def list_my_tools" not in api_source
    assert "submit-review" not in api_source
    assert "pending-reviews" not in api_source
    assert "set-platform" not in api_source
    assert "ToolReviewRequest" not in api_source
    assert "ToolReviewResponse" not in api_source
    assert "SetPlatformToolRequest" not in api_source

    assert "class ToolReviewRequest" not in schema_source
    assert "class ToolReviewResponse" not in schema_source
    assert "class SetPlatformToolRequest" not in schema_source
    assert "ProviderType =" not in schema_source
    assert "ReviewStatus =" not in schema_source


def test_frontend_api_and_store_no_longer_expose_review_flow():
    """前端 API 与 store 不应再暴露审核流或我的工具状态。"""
    api_source = read_source("frontend/src/api/tools.ts")
    store_source = read_source("frontend/src/stores/tools.ts")
    types_source = read_source("frontend/src/types/models.d.ts")

    assert "getMyToolList" not in api_source
    assert "submitToolReview" not in api_source
    assert "adminReviewTool" not in api_source
    assert "adminSetPlatformTool" not in api_source
    assert "adminGetPendingReviews" not in api_source
    assert "/tools/my" not in api_source
    assert "submit-review" not in api_source
    assert "pending-reviews" not in api_source
    assert "set-platform" not in api_source
    assert "provider_type?" not in api_source

    assert "myTools" not in store_source
    assert "pendingReviewTools" not in store_source
    assert "fetchMyTools" not in store_source
    assert "fetchPendingReviewTools" not in store_source
    assert "submitReview" not in store_source
    assert "reviewTool" not in store_source
    assert "provider_type" not in store_source
    assert "review_status" not in store_source

    assert "ToolProviderType" not in types_source
    assert "ToolReviewStatus" not in types_source
    assert "ToolReviewRequest" not in types_source
    assert "ToolReviewResponse" not in types_source
    assert "SetPlatformToolRequest" not in types_source
    assert "ToolView = 'public' | 'my' | 'favorites'" not in types_source
    assert "provider_type:" not in types_source
    assert "review_status:" not in types_source


def test_public_tool_entrypoints_are_pruned_from_main_flow():
    """普通用户入口不应再暴露创建工具和我的工具视图。"""
    router_source = read_source("frontend/src/router/index.ts")
    list_source = read_source("frontend/src/views/tools/List.vue")
    create_source = read_source("frontend/src/views/tools/Create.vue")

    assert "path: '/tools/create'" not in router_source
    assert "name: 'ToolCreate'" not in router_source
    assert "name: 'ToolEdit'" not in router_source

    assert "tools.myTools" not in list_source
    assert "currentView === 'my'" not in list_source
    assert "tools.reviewStatus" not in list_source
    assert "tools.providerType" not in list_source
    assert "goToCreate" not in list_source
    assert "PlusOutlined" not in list_source

    assert "router.push('/tools?view=my')" not in create_source
