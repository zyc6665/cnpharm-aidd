# backend/app/api/v1/__init__.py
"""API v1模块"""

from fastapi import APIRouter
from app.api.v1 import auth, tools, tasks, files, websocket, users, system, verification, agents

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(verification.router, prefix="/verification", tags=["验证码"])
api_router.include_router(users.router, prefix="/users", tags=["用户"])
api_router.include_router(tools.router, prefix="/tools", tags=["工具"])
api_router.include_router(tools.admin_category_router)
api_router.include_router(tools.admin_workbench_group_router)
api_router.include_router(tools.admin_workbench_group_mapping_router)
api_router.include_router(tasks.router, prefix="/tasks", tags=["任务"])
api_router.include_router(files.router, prefix="/files", tags=["文件"])
api_router.include_router(system.router, prefix="/system", tags=["系统"])
api_router.include_router(websocket.router, tags=["WebSocket"])
api_router.include_router(agents.router, prefix="/agents", tags=["智能体"])
