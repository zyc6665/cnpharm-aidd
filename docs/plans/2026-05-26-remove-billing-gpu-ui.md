# 删除充值与 GPU 管理展示 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 保留登录体系，移除前端中的充值/会员/积分中心与 GPU 管理展示入口，同时不触碰底层 GPU 执行逻辑。

**Architecture:** 采用前端产品层收口方案。先用静态表面测试锁定“不可再暴露的路由和 UI 文案”，再最小化修改路由、页面和表单，使用户与管理员界面不再看到充值或 GPU 管理能力。

**Tech Stack:** Vue 3、TypeScript、Ant Design Vue、Vite、Pytest

---

### Task 1: 锁定路由与页面表面行为

**Files:**
- Create: `backend/tests/test_frontend_surface_pruning.py`
- Test: `backend/tests/test_frontend_surface_pruning.py`

**Step 1: Write the failing test**

编写测试，断言以下内容不应继续出现在前端源码中：

- `frontend/src/router/index.ts` 中的 `/credits` 路由
- `frontend/src/views/user/index.vue` 中的积分中心菜单项
- `frontend/src/views/user/Profile.vue` 中跳转 `/credits` 的入口
- `frontend/src/views/admin/System.vue` 中的积分设置与 GPU 信息区块
- `frontend/src/views/admin/Dashboard.vue` 中的 GPU 仪表
- `frontend/src/views/tools/List.vue`、`Detail.vue`、`Create.vue`、`frontend/src/views/admin/Tools.vue` 中的 GPU 可见 UI

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_frontend_surface_pruning.py -v`
Expected: FAIL，因为当前源码仍包含上述入口。

### Task 2: 删除充值相关前端入口

**Files:**
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/views/user/index.vue`
- Modify: `frontend/src/views/user/Profile.vue`
- Modify: `frontend/src/stores/index.ts`

**Step 1: Write minimal implementation**

- 删除 `/credits` 路由
- 删除用户中心侧边栏中的积分中心菜单
- 删除个人资料页中的会员状态/积分信息展示与跳转函数
- 移除 `useCreditsStore` 的对外导出

**Step 2: Run test to verify it still fails only on GPU-related assertions**

Run: `pytest backend/tests/test_frontend_surface_pruning.py -v`
Expected: 充值相关断言转绿，GPU 相关断言仍失败。

### Task 3: 删除 GPU 可见 UI

**Files:**
- Modify: `frontend/src/views/admin/System.vue`
- Modify: `frontend/src/views/admin/Dashboard.vue`
- Modify: `frontend/src/views/admin/Tools.vue`
- Modify: `frontend/src/views/tools/List.vue`
- Modify: `frontend/src/views/tools/Detail.vue`
- Modify: `frontend/src/views/tools/Create.vue`

**Step 1: Write minimal implementation**

- 删除后台系统页中的积分设置标签页与 GPU 信息展示
- 删除后台仪表板中的 GPU 使用率/显存展示
- 删除后台工具创建/编辑弹窗中的 GPU 开关
- 删除工具列表与工具详情页中的 GPU 标签/卡片
- 删除工具创建页中的 GPU 表单项，但保留内部字段与提交兼容逻辑

**Step 2: Run test to verify it passes**

Run: `pytest backend/tests/test_frontend_surface_pruning.py -v`
Expected: PASS

### Task 4: 验证构建与核心后端运行

**Files:**
- No code changes

**Step 1: Run frontend build**

Run: `npm run build`
Workdir: `frontend`
Expected: exit 0

**Step 2: Run backend health validation**

Run: `curl -sS http://127.0.0.1:8002/health`
Expected: 返回健康 JSON

**Step 3: Optional targeted API smoke checks**

Run:
- `curl -sS http://127.0.0.1:8002/api/v1/tools`
- `curl -sS http://127.0.0.1:8002/api/v1/system/health`

Expected: 核心工具/系统接口仍可访问

## 备注

- 按仓库当前协作约束，本次不自动创建 git commit。
- 若后续需要进一步去掉积分成本、会员文案或底层 GPU 队列，可作为下一阶段单独变更。
