# 工具工作台与产物复用 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将现有强流程 `/workflow` 页面改造成按分组导航的工具工作台，并在工作台和普通工具详情页中支持“从我的产物选择”来复用当前用户自己的历史输出文件。

**Architecture:** 后端新增独立的工作台分组与工具映射模型，不复用工具分类。前端保留 `/workflow` 路由，但把页面语义切换成分组工作台，并引入一个共享的产物文件选择器，统一把历史输出文件回填为现有任务提交协议中的 `file_ids`。

**Tech Stack:** FastAPI、SQLAlchemy、Pydantic、Vue 3、TypeScript、Pinia、Vue Router、Ant Design Vue、Pytest、Node Test Runner、Vite

---

### Task 1: 为工作台分组模型建立后端测试基线

**Files:**
- Create: `test/test_tool_workbench_groups.py`
- Test: `test/test_tool_workbench_groups.py`

**Step 1: Write the failing test**

编写测试，断言以下对象将出现：

- `ToolWorkbenchGroup` 模型
- `ToolWorkbenchGroupMapping` 模型
- 分组与工具映射 schema

**Step 2: Run test to verify it fails**

Run: `pytest test/test_tool_workbench_groups.py -v`
Expected: FAIL，因为模型和 schema 还不存在。

### Task 2: 新增工作台分组模型与 schema

**Files:**
- Modify: `backend/app/models/tools.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/schemas/tools.py`
- Test: `test/test_tool_workbench_groups.py`

**Step 1: Write minimal implementation**

- 在 `tools.py` 中新增：
  - `ToolWorkbenchGroup`
  - `ToolWorkbenchGroupMapping`
- 增加与 `Tool` 的关系定义
- 在 `schemas/tools.py` 中补：
  - 分组创建/更新/响应 schema
  - 映射创建/更新/响应 schema

**Step 2: Run test to verify it passes**

Run: `pytest test/test_tool_workbench_groups.py -v`
Expected: 模型与 schema 相关断言 PASS。

**Step 3: Commit**

```bash
git add test/test_tool_workbench_groups.py backend/app/models/tools.py backend/app/models/__init__.py backend/app/schemas/tools.py
git commit -m "feat: add tool workbench group models"
```

### Task 3: 为工作台分组迁移脚本建立基线

**Files:**
- Create: `backend/scripts/create_tool_workbench_groups.sql`
- Create: `backend/scripts/verify_tool_workbench_groups.sql`
- Test: `test/test_tool_workbench_groups.py`

**Step 1: Write the failing test**

补充测试，断言迁移脚本文件存在，并且 SQL 中包含两张新表和唯一约束。

**Step 2: Run test to verify it fails**

Run: `pytest test/test_tool_workbench_groups.py -v`
Expected: FAIL，因为脚本还不存在。

**Step 3: Write minimal implementation**

- 创建工作台分组表
- 创建工具分组映射表
- 增加必要索引和唯一约束
- 补充简单校验 SQL

**Step 4: Run test to verify it passes**

Run: `pytest test/test_tool_workbench_groups.py -v`
Expected: PASS

### Task 4: 为管理端分组与映射 API 建立权限测试

**Files:**
- Create: `test/test_admin_tool_workbench_groups.py`
- Test: `test/test_admin_tool_workbench_groups.py`

**Step 1: Write the failing test**

覆盖：

- 管理员可创建/更新/排序分组
- 管理员可创建/更新/删除工具映射
- 非管理员不能访问

**Step 2: Run test to verify it fails**

Run: `pytest test/test_admin_tool_workbench_groups.py -v`
Expected: FAIL，因为接口尚未实现。

### Task 5: 实现管理端工作台分组与映射 API

**Files:**
- Modify: `backend/app/api/v1/tools.py`
- Modify: `backend/app/api/v1/__init__.py`
- Modify: `backend/app/schemas/tools.py`
- Test: `test/test_admin_tool_workbench_groups.py`

**Step 1: Write minimal implementation**

- 新增管理员接口：
  - `GET/POST/PUT /admin/workbench-groups`
  - `POST /admin/workbench-groups/reorder`
  - `GET/POST/PUT/DELETE /admin/workbench-group-mappings`
- 做最小权限校验与唯一约束处理

**Step 2: Run test to verify it passes**

Run: `pytest test/test_admin_tool_workbench_groups.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add test/test_admin_tool_workbench_groups.py backend/app/api/v1/tools.py backend/app/api/v1/__init__.py backend/app/schemas/tools.py
git commit -m "feat: add admin workbench group management"
```

### Task 6: 为前台工作台分组读取接口建立测试

**Files:**
- Create: `test/test_tool_workbench_public_api.py`
- Test: `test/test_tool_workbench_public_api.py`

**Step 1: Write the failing test**

覆盖：

- `GET /api/v1/tools/workbench-groups` 返回启用分组
- 组内只返回当前可见工具
- 推荐标记与排序正确

**Step 2: Run test to verify it fails**

Run: `pytest test/test_tool_workbench_public_api.py -v`
Expected: FAIL，因为接口未实现。

### Task 7: 实现前台工作台分组读取接口

**Files:**
- Modify: `backend/app/api/v1/tools.py`
- Modify: `backend/app/schemas/tools.py`
- Test: `test/test_tool_workbench_public_api.py`

**Step 1: Write minimal implementation**

- 新增 `GET /api/v1/tools/workbench-groups`
- 按分组排序和组内排序组装公开工具列表
- 返回推荐标记与基础工具摘要

**Step 2: Run test to verify it passes**

Run: `pytest test/test_tool_workbench_public_api.py -v`
Expected: PASS

### Task 8: 为“我的产物”接口建立测试

**Files:**
- Create: `test/test_file_artifacts_api.py`
- Test: `test/test_file_artifacts_api.py`

**Step 1: Write the failing test**

覆盖：

- 只返回当前登录用户自己的工具输出文件
- 不返回他人输出文件
- 不返回普通上传文件
- 返回任务和工具摘要字段

**Step 2: Run test to verify it fails**

Run: `pytest test/test_file_artifacts_api.py -v`
Expected: FAIL，因为接口尚未存在。

### Task 9: 实现“我的产物”后端接口

**Files:**
- Modify: `backend/app/api/v1/files.py`
- Modify: `backend/app/schemas/files.py`
- Test: `test/test_file_artifacts_api.py`

**Step 1: Write minimal implementation**

- 新增 `GET /api/v1/files/artifacts`
- 基于 `TaskOutput.file_ids + File` 聚合用户自己的输出文件
- 返回下载地址、来源任务和来源工具信息

**Step 2: Run test to verify it passes**

Run: `pytest test/test_file_artifacts_api.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add test/test_tool_workbench_public_api.py test/test_file_artifacts_api.py backend/app/api/v1/tools.py backend/app/api/v1/files.py backend/app/schemas/files.py backend/app/schemas/tools.py
git commit -m "feat: add workbench groups and user artifacts apis"
```

### Task 10: 为前端工作台分组页和产物选择器建立表面测试

**Files:**
- Create: `frontend/test/tool-workbench-surface.test.ts`
- Test: `frontend/test/tool-workbench-surface.test.ts`

**Step 1: Write the failing test**

断言：

- `/workflow` 页面文案改成工具工作台
- 页面包含分组栏而不是步骤栏
- 存在产物文件选择器组件
- 普通工具详情页引用了产物选择器

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/tool-workbench-surface.test.ts"`
Expected: FAIL

### Task 11: 增加前端 API 与 store 支撑

**Files:**
- Modify: `frontend/src/api/tools.ts`
- Modify: `frontend/src/api/files.ts`
- Modify: `frontend/src/stores/tools.ts`
- Create: `frontend/src/stores/artifacts.ts`
- Test: `frontend/test/tool-workbench-surface.test.ts`

**Step 1: Write minimal implementation**

- 新增前端 API：
  - `getWorkbenchGroups`
  - `adminGetWorkbenchGroups`
  - `adminGetWorkbenchGroupMappings`
  - `getArtifactFiles`
- 新增或补充 store：
  - 工作台分组数据
  - 用户产物列表数据

**Step 2: Run test to verify partial pass**

Run: `node --test "frontend/test/tool-workbench-surface.test.ts"`
Expected: API/store 相关断言 PASS，页面断言仍失败。

### Task 12: 实现后台工作台分组管理页

**Files:**
- Create: `frontend/src/views/admin/WorkbenchGroups.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/layouts/AdminLayout.vue`
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`
- Test: `frontend/test/tool-workbench-surface.test.ts`

**Step 1: Write the failing test**

补充断言：

- 管理后台有工作台分组管理路由
- 后台导航有入口
- 页面存在分组和映射维护区

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/tool-workbench-surface.test.ts"`
Expected: FAIL

**Step 3: Write minimal implementation**

- 新建后台页面
- 支持分组 CRUD
- 支持映射 CRUD
- 暂时使用最直接的列表 + 表单布局

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/tool-workbench-surface.test.ts"`
Expected: 后台入口相关断言 PASS。

### Task 13: 实现共享产物文件选择器

**Files:**
- Create: `frontend/src/components/tools/ArtifactFilePicker.vue`
- Modify: `frontend/src/views/tools/detail-schema.ts`
- Test: `frontend/test/tool-workbench-surface.test.ts`

**Step 1: Write the failing test**

补充断言：

- 存在 `ArtifactFilePicker.vue`
- 工具详情页文件型参数支持“上传 / 从我的产物选择”
- 选择器最终能返回已有 `file_id`

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/tool-workbench-surface.test.ts"`
Expected: FAIL

**Step 3: Write minimal implementation**

- 新建选择器组件
- 支持当前用户产物列表加载
- 支持选中已有文件并回填表单
- 保持现有 `buildTaskSubmissionPayload` 仍只消费 `file_ids`

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/tool-workbench-surface.test.ts"`
Expected: PASS

### Task 14: 将普通工具详情页接入产物选择器

**Files:**
- Modify: `frontend/src/views/tools/Detail.vue`
- Modify: `frontend/src/views/tools/detail-schema.ts`
- Test: `frontend/test/tool-workbench-surface.test.ts`

**Step 1: Write the failing test**

补充断言：

- `/tools/:id` 中的文件字段会渲染产物选择器
- 仍保留本地上传能力

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/tool-workbench-surface.test.ts"`
Expected: FAIL

**Step 3: Write minimal implementation**

- 用共享组件替换原文件型字段的单一上传入口
- 保持未登录时降级为纯上传

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/tool-workbench-surface.test.ts"`
Expected: PASS

### Task 15: 将 `/workflow` 从流程语义迁移为分组工作台

**Files:**
- Modify: `frontend/src/views/workflow/index.vue`
- Modify: `frontend/src/components/workflow/WorkflowStepSidebar.vue`
- Modify: `frontend/src/components/workflow/WorkflowRunPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowArtifactPanel.vue`
- Modify: `frontend/src/stores/workflow.ts`
- Modify: `frontend/src/workflow/aidd-catalog.ts`
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`
- Test: `frontend/test/tool-workbench-surface.test.ts`

**Step 1: Write the failing test**

补充断言：

- 页面标题改成工具工作台
- 左栏改成分组栏
- 不再出现“下一步”“结果失效”之类强流程文案
- 右栏改成“我的产物”

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/tool-workbench-surface.test.ts"`
Expected: FAIL

**Step 3: Write minimal implementation**

- 把左栏数据源切成工作台分组
- 去掉步骤状态机和自动流转文案
- 中栏改成“分组工具 + 当前工具表单”
- 右栏接入真实产物列表

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/tool-workbench-surface.test.ts"`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/components/tools/ArtifactFilePicker.vue frontend/src/views/tools/Detail.vue frontend/src/views/tools/detail-schema.ts frontend/src/views/workflow/index.vue frontend/src/components/workflow/WorkflowStepSidebar.vue frontend/src/components/workflow/WorkflowRunPanel.vue frontend/src/components/workflow/WorkflowArtifactPanel.vue frontend/src/stores/workflow.ts frontend/src/stores/artifacts.ts frontend/src/locales/zh-CN/index.ts frontend/src/locales/en-US/index.ts frontend/src/views/admin/WorkbenchGroups.vue frontend/src/router/index.ts frontend/src/layouts/AdminLayout.vue frontend/test/tool-workbench-surface.test.ts
git commit -m "feat: add tool workbench and artifact reuse"
```

### Task 16: 完成整体验证

**Files:**
- Test: `test/test_tool_workbench_groups.py`
- Test: `test/test_admin_tool_workbench_groups.py`
- Test: `test/test_tool_workbench_public_api.py`
- Test: `test/test_file_artifacts_api.py`
- Test: `frontend/test/tool-workbench-surface.test.ts`

**Step 1: Run backend test suite**

Run: `pytest test/test_tool_workbench_groups.py test/test_admin_tool_workbench_groups.py test/test_tool_workbench_public_api.py test/test_file_artifacts_api.py -v`
Expected: PASS

**Step 2: Run frontend test suite**

Run: `node --test "frontend/test/tool-workbench-surface.test.ts"`
Expected: PASS

**Step 3: Run type check**

Run: `./node_modules/.bin/vue-tsc -b`
Expected: PASS

**Step 4: Run build**

Run: `npm run build`
Expected: PASS

**Step 5: Smoke check key pages**

检查：

- 后台工作台分组管理页可打开
- `/workflow` 工具工作台可打开
- 工具详情页文件字段能选择“我的产物”

**Step 6: Commit**

```bash
git add .
git commit -m "test: verify tool workbench artifact reuse"
```
