"""工具 API 兼容聚合入口。

具体路由分别位于 tools_public、tools_admin 与 tool_versions 模块。
"""

from fastapi import APIRouter

from app.api.v1.tool_versions import router as version_router
from app.api.v1.tools_admin import router as admin_router
from app.api.v1.tools_public import router as public_router

router = APIRouter()
router.routes.extend(public_router.routes)
router.routes.extend(admin_router.routes)
router.routes.extend(version_router.routes)
