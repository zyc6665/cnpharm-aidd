# 科研白板功能退役实施计划

> **Goal:** 移除科研白板产品入口及专属 API，同时保留历史表、历史数据和独立 Artifact/Workflow/蛋白制备能力。
>
> **Architecture:** 删除前端白板页面和导航；后端取消白板 API 与聚合响应；剥离外部数据库导入和蛋白制备对画布的副作用。`ResearchBoard` 模型只留作历史数据兼容和既有删除/迁移处理。
>
> **Tech Stack:** Vue 3, TypeScript, FastAPI, SQLAlchemy, Pydantic, pytest, Vitest.

---

### Task 1: 移除前端白板入口和页面

**Files:** `frontend/src/router/index.ts`, `frontend/src/components/layout/AppShell.vue`, `frontend/src/domain/projects/navigation.ts`, `frontend/src/views/projects/Overview.vue`, `frontend/src/domain/projects/overview.ts`, `frontend/src/types/projects.ts`, `frontend/src/api/workspace.ts`, `frontend/src/api/index.ts`, `frontend/src/views/research-boards/**`, `frontend/src/components/research-boards/**`, `frontend/src/api/research-boards.ts`, `frontend/src/api/protein-preparation.ts`.

移除白板全局/项目路由、导航、总览卡片与列表、API 导出和白板专属页面/组件。同步更新 overview、导航及页面规格，保留项目任务、Artifact、Workflow、谱系和设置入口。

### Task 2: 移除后端白板运行表面

**Files:** `backend/app/api/v1/__init__.py`, `backend/app/api/v1/research_boards.py`, `backend/app/api/v1/protein_preparation.py`, `backend/app/api/v1/projects.py`, `backend/app/api/v1/workspace.py`, `backend/app/config.py`, `backend/app/schemas/external_databases.py`.

取消白板与白板节点蛋白制备路由注册；项目和工作台接口不再查询、计数或序列化白板；删除白板 Feature Flag。保留项目删除、用户删除、项目数据回填中的历史 `ResearchBoard` 清理和迁移支持。

### Task 3: 剥离白板专属 Artifact 集成

**Files:** `backend/app/external_databases/imports.py`, `backend/app/api/v1/external_databases.py`, `backend/app/schemas/protein_preparation.py`, `frontend/src/api/external-databases.ts`.

外部数据库导入只创建标准 Artifact，不再接受白板 ID/画布坐标或返回画布节点。蛋白制备参数模型保留计算选项，移除仅服务于白板节点布局和同步的请求模型及路由。

### Task 4: 更新测试和当前产品文档

**Files:** `test/test_research_boards_api.py`, `test/test_project_research_boards_api.py`, `test/test_protein_preparation_board_api.py`, `test/test_protein_preparation_workflow_api.py`, `test/test_projects_api.py`, `test/test_workspace_overview_api.py`, `test/test_external_database_import_api.py`, `test/test_config_security.py`, `test/test_admin_system_routes.py`, `frontend/src/views/projects/Overview.spec.ts`, `frontend/src/domain/projects/navigation.spec.ts`, `frontend/src/domain/projects/overview.spec.ts`, `docs/product/**`, `docs/architecture/01-平台总体架构.md`, `docs/architecture/02-核心领域设计.md`, `docs/delivery/01-企业交付需求规格说明书.md`.

移除白板路由和响应字段断言；保留历史表迁移、旧数据回填和清理断言。更新当前产品/架构说明，历史计划文件按历史记录保留。

### Task 5: 静态验证

运行前端生产构建、后端应用编译和 `git diff --check`。检查剩余白板引用只位于历史文档、旧数据兼容清理及迁移中。
