# Home Platform Foundation Section Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将首页“平台特性”四卡区块替换为更高质量的双栏叙事区，分别介绍 CPUModel 当前平台模型与 CPUPDB 的数据支撑价值，并保持视觉风格与首页整体一致。

**Architecture:** 仅改首页中段内容结构与文案键，不改后端和全局布局。首页模板改为双栏叙事甲板，locale 从 `home.features` 迁移到新的 `home.foundation`，并通过表面测试锁定新结构与 CPUPDB 外链。

**Tech Stack:** Vue 3、TypeScript、Vue I18n、Ant Design Vue、Node Test Runner、Vite

---

### Task 1: 为首页新介绍区写失败测试

**Files:**
- Modify: `frontend/test/global-ui-refresh-surface.test.ts` 或创建新的首页表面测试文件
- Test: `frontend/test/...`

**Step 1: Write the failing test**

覆盖以下断言：

- 首页源码不应继续依赖旧的 `home.features.items.cloud/api/security`
- 首页应出现新的 `home.foundation` 区块引用
- 首页应包含 `CPUModel` 与 `CPUPDB` 两栏语义
- 首页应包含指向 `https://www.cpupdb.com` 的外链

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/<home-surface-test>.ts"`

Expected:

- FAIL，因为首页仍然是旧的特性卡片结构

### Task 2: 更新中英文 locale 为新文案模型

**Files:**
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`
- Test: `frontend/test/<home-surface-test>.ts`

**Step 1: Add new foundation copy**

新增：

- `home.foundation.title`
- `home.foundation.subtitle`
- `home.foundation.platform.*`
- `home.foundation.cpupdb.*`

文案口径按设计稿执行，并保持中英文结构一致。

**Step 2: Remove stale feature dependencies**

不要强行删除所有 `home.features` 键，但首页实现不再依赖它们。

**Step 3: Run test**

Run: `node --test "frontend/test/<home-surface-test>.ts"`

Expected:

- 仍可能 FAIL，因为首页模板尚未切换

### Task 3: 重构首页中段模板与数据结构

**Files:**
- Modify: `frontend/src/views/home/index.vue`
- Test: `frontend/test/<home-surface-test>.ts`

**Step 1: Replace features section**

把当前 Features Section 替换为新的 `foundation-section`：

- 区块总标题
- 左栏 `CPUModel`
- 右栏 `CPUPDB`

**Step 2: Remove obsolete feature icon config**

移除旧 `features` 对象和不再使用的图标引用，避免死代码残留。

**Step 3: Add links**

左栏按钮跳转 `/workflow`

右栏按钮使用外链：

- `https://www.cpupdb.com`

可选帮助链接：

- `https://www.cpupdb.com/help.html`

**Step 4: Run test**

Run: `node --test "frontend/test/<home-surface-test>.ts"`

Expected:

- PASS

### Task 4: 实现新的双栏叙事视觉样式

**Files:**
- Modify: `frontend/src/views/home/index.vue`
- Test: `npm run build`

**Step 1: Add section styles**

新增样式类，例如：

- `foundation-section`
- `foundation-shell`
- `foundation-grid`
- `foundation-panel`
- `foundation-kicker`
- `foundation-points`

**Step 2: Preserve homepage visual language**

保持与 Hero 同系的科研感，但降低对比，避免整页都像头图。

**Step 3: Ensure responsive layout**

桌面端双栏，移动端纵向堆叠。

### Task 5: 回归验证与构建

**Files:**
- Test: `frontend/test/<home-surface-test>.ts`

**Step 1: Run targeted tests**

Run:

- `node --test "frontend/test/<home-surface-test>.ts"`

Expected:

- PASS

**Step 2: Run build**

Run: `npm run build`

Workdir: `frontend/`

Expected:

- Build succeeds
- 允许保留既有非阻塞 Vite 警告，但不能新增错误
