# backend/app/api/v1/__init__.py
"""API v1模块"""

from fastapi import APIRouter
from app.api.v1 import (
    agent_stream,
    agents,
    auth,
    conversations,
    files,
    projects,
    research_boards,
    system,
    tasks,
    tool_packages,
    workspace,
    tool_categories,
    tool_workbench_admin,
    tools,
    users,
    verification,
    websocket,
    workflows,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(verification.router, prefix="/verification", tags=["验证码"])
api_router.include_router(users.router, prefix="/users", tags=["用户"])
api_router.include_router(tools.router, prefix="/tools", tags=["工具"])
api_router.include_router(tool_packages.router, prefix="/tool-packages", tags=["工具包"])
api_router.include_router(tool_categories.router)
api_router.include_router(tool_workbench_admin.group_router)
api_router.include_router(tool_workbench_admin.mapping_router)
api_router.include_router(tasks.router, prefix="/tasks", tags=["任务"])
api_router.include_router(files.router, prefix="/files", tags=["文件"])
api_router.include_router(projects.router, prefix="/projects", tags=["研究项目"])
api_router.include_router(conversations.router, tags=["项目会话"])
api_router.include_router(agent_stream.router, tags=["智能体事件"])
api_router.include_router(system.router, prefix="/system", tags=["系统"])
api_router.include_router(websocket.router, tags=["WebSocket"])
api_router.include_router(agents.router, prefix="/agents", tags=["智能体"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["工作流"])
api_router.include_router(research_boards.router, prefix="/research-boards", tags=["科研白板"])
api_router.include_router(workspace.router, prefix="/workspace", tags=["工作台"])
