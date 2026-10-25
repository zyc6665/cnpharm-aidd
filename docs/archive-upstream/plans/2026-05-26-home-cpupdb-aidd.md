# 首页 CPUPDB 导航与 AIDD 流程改造 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为首页新增 `CPUPDB` 导航占位入口，并把第二屏改造成按 AIDD 顺序展示的平台功能流程。

**Architecture:** 采用前端静态表面改造方案。先用源码测试锁定导航入口、文案键和流程顺序，再最小化修改布局组件、首页视图和 locale 文案，不引入新路由或全局配置。

**Tech Stack:** Vue 3、TypeScript、Vue I18n、Ant Design Vue、Vite、Node Test Runner

---

### Task 1: 锁定首页与导航目标表面

**Files:**
- Create: `frontend/test/home-cpupdb-aidd.test.ts`
- Test: `frontend/test/home-cpupdb-aidd.test.ts`

**Step 1: Write the failing test**

编写源码测试，断言：

- `frontend/src/components/layout/DefaultLayout.vue` 包含 `CPUPDB` 导航占位入口
- `frontend/src/views/home/index.vue` 包含 AIDD 流程数组与箭头展示
- `frontend/src/locales/zh-CN/index.ts` 与 `frontend/src/locales/en-US/index.ts` 包含“平台功能”和五个流程步骤文案

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/home-cpupdb-aidd.test.ts"`
Expected: FAIL，因为当前导航和首页尚未包含这些内容

### Task 2: 实现导航中的 CPUPDB 占位入口

**Files:**
- Modify: `frontend/src/components/layout/DefaultLayout.vue`

**Step 1: Write minimal implementation**

- 在组件脚本中定义 `cpupdbUrl` 常量，值为 `https://www.cpupdb.com`
- 在顶部导航中新增一个外链菜单项
- 使用 `t('nav.cpupdb')` 作为菜单文案

**Step 2: Run test to verify only首页相关断言仍可能失败**

Run: `node --test "frontend/test/home-cpupdb-aidd.test.ts"`
Expected: 导航相关断言转绿，首页流程相关断言仍失败

### Task 3: 将首页第二屏改造成 AIDD 平台功能流程

**Files:**
- Modify: `frontend/src/views/home/index.vue`
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`

**Step 1: Write minimal implementation**

- 将第二屏标题改为“平台功能”
- 把原 4 卡片结构改为 5 步流程结构：
  - 口袋探索
  - 分子生成或虚拟筛选
  - 分子对接及结合亲和力预测
  - 性质预测
  - 先导化合物优化
- 用箭头连接相邻步骤
- 桌面端保持横向流程，移动端纵向堆叠
- 补齐中英文 locale 文案

**Step 2: Run test to verify it passes**

Run: `node --test "frontend/test/home-cpupdb-aidd.test.ts"`
Expected: PASS

### Task 4: 回归验证

**Files:**
- No code changes

**Step 1: Run targeted source tests**

Run:
- `node --test "frontend/test/home-cpupdb-aidd.test.ts"`
- `node --test "frontend/test/product-surface-pruning.test.ts"`

Expected: PASS

**Step 2: Run frontend build**

Run: `npm run build`
Workdir: `frontend`
Expected: exit 0

## 备注

- 本次不自动创建 git commit
- `CPUPDB` 地址当前为 `https://www.cpupdb.com`
