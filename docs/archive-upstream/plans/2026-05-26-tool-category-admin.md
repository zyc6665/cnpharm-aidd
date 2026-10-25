# 工具分类独立化与管理员收口 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 引入独立的工具分类表，允许管理员管理分类，并把工具创建/编辑/删除权限完全收口到管理员。

**Architecture:** 先在数据库层引入 `tool_categories` 和 `tools.category_id`，用迁移脚本承接旧的 `tools.category` 文本数据；随后新增管理员分类 API、收紧工具写权限，再改前端管理后台和普通用户入口，最终下线用户工具与审核流。

**Tech Stack:** FastAPI、SQLAlchemy、SQLite、Vue 3、TypeScript、Pinia、Ant Design Vue、Pytest

---

### Task 1: 为分类主数据建立测试基线

**Files:**
- Create: `test/test_tool_category_management.py`
- Test: `test/test_tool_category_management.py`

**Step 1: Write the failing test**

编写后端测试，覆盖以下行为：

- 存在独立的 `ToolCategory` 模型
- 管理员可创建分类
- 非管理员创建分类返回 `403`
- 有工具引用的分类不可删除

**Step 2: Run test to verify it fails**

Run: `pytest test/test_tool_category_management.py -v`
Expected: FAIL，因为当前仓库还没有独立分类模型和接口。

### Task 2: 建立分类模型与数据库迁移

**Files:**
- Modify: `backend/app/models/tools.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/scripts/create_tool_categories.sql`
- Create: `backend/scripts/migrate_tool_categories.sql`
- Create: `backend/scripts/verify_tool_category_migration.sql`

**Step 1: Write minimal implementation**

- 新增 `ToolCategory` 模型
- 为 `Tool` 增加 `category_id` 外键关系
- 保留旧 `category` 字段作为迁移期兼容读取字段
- 编写 SQL 脚本创建分类表、回填历史分类、校验迁移结果

**Step 2: Run targeted test**

Run: `pytest test/test_tool_category_management.py -v`
Expected: 仍失败，但失败点应从“模型不存在”收敛到“接口/权限未实现”。

### Task 3: 扩展 Schema 并定义分类管理请求/响应

**Files:**
- Modify: `backend/app/schemas/tools.py`

**Step 1: Write the failing test**

在 `test/test_tool_category_management.py` 中补充断言：

- 存在分类创建、更新、状态更新、排序请求模型
- 工具创建/更新请求改为使用 `category_id`
- 工具响应包含 `category_id` 和兼容展示字段 `category`

**Step 2: Run test to verify it fails**

Run: `pytest test/test_tool_category_management.py -v`
Expected: FAIL，因为 Schema 仍未更新。

**Step 3: Write minimal implementation**

- 新增 `ToolCategoryCreate`、`ToolCategoryUpdate`、`ToolCategoryResponse`
- 新增分类状态和重排请求模型
- 调整 `ToolCreate`、`ToolUpdate`、`ToolResponse`、`ToolListResponse`

**Step 4: Run test to verify partial pass**

Run: `pytest test/test_tool_category_management.py -v`
Expected: Schema 相关断言转绿，接口相关断言仍失败。

### Task 4: 实现公开分类读取与管理员分类管理 API

**Files:**
- Modify: `backend/app/api/v1/tools.py`
- Modify: `backend/app/api/v1/__init__.py`
- Test: `test/test_tool_category_management.py`

**Step 1: Write the failing test**

补充 API 行为测试：

- `GET /api/v1/tools/categories` 只返回启用分类
- 管理员可新增、更新、停用、启用、排序分类
- 删除被引用分类返回冲突错误

**Step 2: Run test to verify it fails**

Run: `pytest test/test_tool_category_management.py -v`
Expected: FAIL，因为接口尚未实现。

**Step 3: Write minimal implementation**

- 在 `tools.py` 中引入分类查询和管理逻辑
- 管理员接口统一使用 `get_admin_user`
- 公开列表仅返回启用分类并按 `sort_order` 排序
- 删除接口增加“存在工具引用则禁止删除”的保护

**Step 4: Run test to verify it passes**

Run: `pytest test/test_tool_category_management.py -v`
Expected: PASS

### Task 5: 收紧工具写权限并切换到 `category_id`

**Files:**
- Modify: `backend/app/api/v1/tools.py`
- Modify: `backend/app/auth/dependencies.py`
- Test: `test/test_admin_tool_permissions.py`

**Step 1: Write the failing test**

创建测试覆盖以下行为：

- 普通用户调用工具创建、更新、删除接口返回 `403`
- 管理员创建工具时必须提供有效 `category_id`
- 停用分类不可用于新建或编辑工具

**Step 2: Run test to verify it fails**

Run: `pytest test/test_admin_tool_permissions.py -v`
Expected: FAIL，因为当前仍允许普通用户创建工具。

**Step 3: Write minimal implementation**

- 将工具写接口的依赖统一改为管理员身份
- 移除基于 `provider_type`、`review_status` 的创建分支
- 写入和更新逻辑改为只验证 `category_id`

**Step 4: Run test to verify it passes**

Run: `pytest test/test_admin_tool_permissions.py -v`
Expected: PASS

### Task 6: 下线审核流和用户工具能力

**Files:**
- Modify: `backend/app/api/v1/tools.py`
- Modify: `backend/app/schemas/tools.py`
- Modify: `frontend/src/api/tools.ts`
- Modify: `frontend/src/stores/tools.ts`
- Modify: `frontend/src/types/models.d.ts`
- Test: `test/test_tool_surface_pruning.py`

**Step 1: Write the failing test**

编写静态表面测试，断言以下能力不应再出现在主流程中：

- `/tools/create`
- “我的工具”视图
- 审核状态文案和筛选
- `submit-review`
- `pending-reviews`
- `set-platform`

**Step 2: Run test to verify it fails**

Run: `pytest test/test_tool_surface_pruning.py -v`
Expected: FAIL，因为相关入口仍存在。

**Step 3: Write minimal implementation**

- 删除审核相关接口与前端调用
- 清理 `provider_type` / `review_status` 主流程使用
- 保留收藏能力

**Step 4: Run test to verify it passes**

Run: `pytest test/test_tool_surface_pruning.py -v`
Expected: PASS

### Task 7: 新增管理员分类管理页面

**Files:**
- Create: `frontend/src/views/admin/ToolCategories.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/views/admin/index.vue`
- Modify: `frontend/src/api/tools.ts`
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`

**Step 1: Write the failing test**

编写静态或组件表面测试，断言：

- 管理后台存在分类管理路由
- 侧边栏存在分类管理入口
- 页面中有新增、编辑、启停、删除、排序入口

**Step 2: Run test to verify it fails**

Run: `pytest test/test_admin_tool_category_frontend_surface.py -v`
Expected: FAIL，因为当前页面不存在。

**Step 3: Write minimal implementation**

- 新增后台分类管理页
- 接入管理员分类 API
- 先用表格 + 弹窗 + 上移/下移实现排序，不做拖拽

**Step 4: Run test to verify it passes**

Run: `pytest test/test_admin_tool_category_frontend_surface.py -v`
Expected: PASS

### Task 8: 改造管理员工具页与工具创建/编辑页

**Files:**
- Modify: `frontend/src/views/admin/Tools.vue`
- Modify: `frontend/src/views/tools/Create.vue`
- Modify: `frontend/src/views/tools/List.vue`
- Modify: `frontend/src/stores/tools.ts`
- Modify: `frontend/src/types/models.d.ts`

**Step 1: Write the failing test**

补充前端表面测试：

- 管理员工具表单使用分类接口返回值
- 表单提交字段为 `category_id`
- 普通用户看不到创建工具按钮
- 工具列表仍可按分类筛选

**Step 2: Run test to verify it fails**

Run: `pytest test/test_admin_tool_category_frontend_surface.py -v`
Expected: FAIL，因为当前仍使用硬编码分类和公开创建入口。

**Step 3: Write minimal implementation**

- 管理员工具页改用真实后端数据
- 创建/编辑表单从分类列表中选择 `category_id`
- 删除普通用户创建工具按钮和公开路由入口

**Step 4: Run test to verify it passes**

Run: `pytest test/test_admin_tool_category_frontend_surface.py -v`
Expected: PASS

### Task 9: 执行迁移验证与构建验证

**Files:**
- No code changes

**Step 1: Run backend tests**

Run:
- `pytest test/test_tool_category_management.py -v`
- `pytest test/test_admin_tool_permissions.py -v`
- `pytest test/test_tool_surface_pruning.py -v`
- `pytest test/test_admin_tool_category_frontend_surface.py -v`

Expected: 全部 PASS

**Step 2: Run migration verification**

Run:
- `sqlite3 "backend/storage/scitool.db" < "backend/scripts/verify_tool_category_migration.sql"`

Expected: 输出无异常，且 `tools.category_id` 不存在空值。

**Step 3: Run frontend build**

Run: `npm run build`
Workdir: `frontend`
Expected: exit 0

**Step 4: Run backend smoke checks**

Run:
- `curl -sS http://127.0.0.1:8002/health`
- `curl -sS http://127.0.0.1:8002/api/v1/tools/categories`

Expected: 返回健康 JSON 和启用分类列表。

## 备注

- 按仓库当前协作约束，本计划不包含自动 `git commit` 步骤。
- 若后续需要彻底删除数据库中的 `category`、`provider_type`、`review_status` 历史字段，可在功能稳定后安排二期清理。
