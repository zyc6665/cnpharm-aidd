# backend/app/api/v1/__init__.py
"""API v1模块"""

from fastapi import APIRouter
from app.api.v1 import (
    admin_audit,
    artifacts,
    auth,
    compounds,
    decisions,
    files,
    gpu,
    projects,
    results,
    system,
    targets,
    tasks,
    tool_packages,
    tool_templates,
    workspace,
    tool_categories,
    tool_workbench_admin,
    tools,
    users,
    verification,
    workflows,
    image_assets,
    datasets,
    uploads,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(verification.router, prefix="/verification", tags=["验证码"])
api_router.include_router(users.router, prefix="/users", tags=["用户"])
api_router.include_router(tools.router, prefix="/tools", tags=["工具"])
api_router.include_router(tool_packages.router, prefix="/tool-packages", tags=["工具包"])
api_router.include_router(tool_templates.router, prefix="/tool-templates", tags=["工具模板"])
api_router.include_router(artifacts.router, tags=["科研产物"])
api_router.include_router(tool_categories.router)
api_router.include_router(tool_workbench_admin.group_router)
api_router.include_router(tool_workbench_admin.mapping_router)
api_router.include_router(tasks.router, prefix="/tasks", tags=["任务"])
api_router.include_router(files.router, prefix="/files", tags=["文件"])
api_router.include_router(gpu.router)
api_router.include_router(projects.router, prefix="/projects", tags=["研究项目"])
api_router.include_router(targets.project_router, prefix="/projects", tags=["靶点与结构"])
api_router.include_router(targets.router, tags=["靶点与结构"])
api_router.include_router(compounds.project_router, prefix="/projects", tags=["化合物与候选物"])
api_router.include_router(compounds.router, tags=["化合物与候选物"])
api_router.include_router(decisions.project_router, prefix="/projects", tags=["研发决策与阶段"])
api_router.include_router(results.project_router, prefix="/projects", tags=["结果与追溯"])
api_router.include_router(results.router, tags=["结果与追溯"])
api_router.include_router(system.router, prefix="/system", tags=["系统"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["工作流"])
api_router.include_router(workspace.router, prefix="/workspace", tags=["工作台"])
api_router.include_router(datasets.project_router, prefix="/projects", tags=["数据集"])
api_router.include_router(datasets.router, tags=["数据集"])
api_router.include_router(uploads.router, tags=["分片上传"])
api_router.include_router(image_assets.router, prefix="/admin/image-assets", tags=["管理员镜像资产"])
api_router.include_router(admin_audit.router, prefix="/admin/audit-logs", tags=["管理员审计日志"])
