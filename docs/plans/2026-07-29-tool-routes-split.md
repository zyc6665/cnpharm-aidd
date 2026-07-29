# Tool Routes Split Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将工具 API 的公开、管理、版本和共享逻辑从单体 `tools.py` 拆入独立模块，并保持全部既有接口兼容。

**Architecture:** 三个无前缀子路由依赖单向共享辅助模块，由 `tools.py` 聚合后继续通过原有 `/tools` 前缀挂载。迁移只改变代码所有权，不改变 URL、权限、响应和事务行为。

**Tech Stack:** FastAPI、SQLAlchemy 2.0、Pydantic、pytest、pytest-asyncio

---

### Task 1: 锁定模块边界与兼容入口

**Files:**
- Modify: `test/test_backend_architecture_boundaries.py`
- Create: `backend/app/api/v1/tool_route_utils.py`
- Create: `backend/app/api/v1/tools_public.py`
- Create: `backend/app/api/v1/tools_admin.py`
- Create: `backend/app/api/v1/tool_versions.py`
- Modify: `backend/app/api/v1/tools.py`

**Steps:**
1. 添加失败测试，断言四个新模块可导入、`tools.router` 保持存在且兼容模块不再定义业务端点。
2. 运行 `pytest test/test_backend_architecture_boundaries.py -q`，确认因模块缺失失败。
3. 创建最小模块和路由聚合结构。
4. 再次运行测试并确认通过。
5. 提交 `test(api): define tool route module boundaries`。

### Task 2: 迁移共享辅助逻辑和公开路由

**Files:**
- Modify: `backend/app/api/v1/tool_route_utils.py`
- Modify: `backend/app/api/v1/tools_public.py`
- Modify: `backend/app/api/v1/tools.py`
- Test: `test/test_api.py`
- Test: `test/test_tool_examples_api.py`
- Test: `test/test_tool_favorites_api.py`
- Test: `test/test_tool_workbench_public_api.py`
- Test: `test/test_tool_contracts.py`

**Steps:**
1. 扩展模块布局测试，要求公开路由模块拥有列表、详情、示例、契约、收藏和工作台入口。
2. 运行测试并确认失败。
3. 将共享序列化、加载和契约辅助函数迁入 `tool_route_utils.py`，将公开端点迁入 `tools_public.py`。
4. 运行公开工具 API 聚焦测试并确认通过。
5. 提交 `refactor(api): extract public tool routes`。

### Task 3: 迁移管理员工具路由

**Files:**
- Modify: `backend/app/api/v1/tool_route_utils.py`
- Modify: `backend/app/api/v1/tools_admin.py`
- Modify: `backend/app/api/v1/tools.py`
- Test: `test/test_admin_tool_permissions.py`
- Test: `test/test_tool_import_api.py`
- Test: `test/test_tool_import_config.py`

**Steps:**
1. 添加失败测试，要求管理员模块拥有导入、创建、更新、删除、发布和标签创建端点。
2. 运行测试并确认失败。
3. 迁移管理员路由及导入服务辅助逻辑。
4. 运行管理员权限与导入聚焦测试并确认通过。
5. 提交 `refactor(api): extract admin tool routes`。

### Task 4: 迁移版本路由并收敛兼容模块

**Files:**
- Modify: `backend/app/api/v1/tool_versions.py`
- Modify: `backend/app/api/v1/tools.py`
- Test: `test/test_tool_version_manager.py`
- Test: `test/test_backend_architecture_boundaries.py`

**Steps:**
1. 添加失败测试，要求版本模块拥有列表和创建端点，兼容模块只聚合子路由。
2. 运行测试并确认失败。
3. 迁移版本端点，删除 `tools.py` 中剩余业务实现。
4. 运行版本和架构聚焦测试并确认通过。
5. 提交 `refactor(api): extract tool version routes`。

### Task 5: 完整回归验证

**Files:**
- Verify: `backend/app/api/v1/*.py`
- Verify: `test/`
- Verify: `frontend/`

**Steps:**
1. 运行所有工具 API 聚焦测试。
2. 运行 `pytest test`。
3. 运行 `npm run test -- --run` 和 `npm run build`。
4. 运行 `python -m compileall -q backend/app/api/v1` 与 `git diff --check`。
5. 如需测试同步修正，单独提交；确认工作区只保留既有本地未跟踪文件。
