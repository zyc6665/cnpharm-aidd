# Global UI Refresh Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 CPUModel 前端完成一轮全站统一 UI 改造，建立“深空实验甲板”视觉系统，并统一用户侧与管理侧的布局、组件和页面气质。

**Architecture:** 先重建全局视觉 token 和 Ant Design Vue 主题覆盖，再把默认布局、公共页头、筛选条和通用面板收口为共享壳层，最后将首页、工具页、工作台、任务页和管理后台映射到同一品牌语言。整个改造保持 DRY/YAGNI，只重做实际生效的壳层和核心页面，不动未接线路由和未使用布局。

**Tech Stack:** Vue 3、TypeScript、Less、Ant Design Vue、Vue Router、Node Test Runner、Vite

> 注：按仓库约束，本计划不包含 `git commit` / `git push` / 分支操作。

---

### Task 1: 为全站 UI 改造建立失败测试

**Files:**
- Create: `frontend/test/global-ui-refresh-surface.test.ts`
- Test: `frontend/test/global-ui-refresh-surface.test.ts`

**Step 1: Write the failing test**

在 `frontend/test/global-ui-refresh-surface.test.ts` 中增加源码断言，覆盖以下表面能力：

- `frontend/src/assets/styles/variables.less` 暴露新的全局视觉 token，例如：

```ts
assert.equal(source.includes('@brand-gold'), true)
assert.equal(source.includes('@brand-cyan'), true)
assert.equal(source.includes('@surface-1'), true)
assert.equal(source.includes('@font-family-heading'), true)
```

- `frontend/src/assets/styles/antd-override.less` 为 AntD 声明新的 `:root` 主题变量和深色组件表面
- `frontend/src/components/layout/DefaultLayout.vue` 包含新的统一壳层类名，例如 `shell-backdrop`、`header-chrome`、`nav-pill`
- `frontend/src/components/common/AppPageHeader.vue` 和 `frontend/src/components/common/AppFilterBar.vue` 使用新的统一视觉类名
- `frontend/src/views/admin/index.vue` 使用管理端统一壳层，而不是继续保持完全默认后台风

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/global-ui-refresh-surface.test.ts"`
Expected: FAIL，因为新的 token、壳层类名和主题覆盖尚未实现。

### Task 2: 重建全局视觉 token 和基础主题

**Files:**
- Modify: `frontend/src/assets/styles/variables.less`
- Modify: `frontend/src/assets/styles/global.less`
- Modify: `frontend/src/assets/styles/antd-override.less`
- Modify: `frontend/src/App.vue`
- Test: `frontend/test/global-ui-refresh-surface.test.ts`

**Step 1: Write minimal implementation**

在 `frontend/src/assets/styles/variables.less` 中重建一套“深空实验甲板” token，至少包含：

```less
@brand-gold: #f3c969;
@brand-gold-soft: rgba(243, 201, 105, 0.18);
@brand-cyan: #7ce0d3;
@brand-cyan-soft: rgba(124, 224, 211, 0.18);
@ink-990: #08111f;
@ink-950: #0d1728;
@ink-900: #122033;
@surface-1: rgba(10, 19, 34, 0.78);
@surface-2: rgba(16, 28, 46, 0.88);
@surface-3: rgba(255, 255, 255, 0.06);
@border-strong: rgba(124, 224, 211, 0.22);
@border-soft: rgba(255, 255, 255, 0.08);
@font-family-heading: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
@font-family-body: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
@font-family-mono: 'JetBrains Mono', 'SFMono-Regular', Consolas, monospace;
```

同步重写：

- `card()` mixin：改为半透明深色面板，不再是纯白卡片
- 页面阴影、边框、圆角、间距层级
- 浅色文本 token，避免在后台内容区出现灰度混乱

在 `frontend/src/assets/styles/global.less` 中补齐：

- `body` / `#app` 的统一深色背景和网格氛围
- `page-shell`、`panel-surface`、`panel-muted` 等共享类
- 通用按钮、链接、空态、滚动条和页面过渡样式

在 `frontend/src/assets/styles/antd-override.less` 中：

- 用新的品牌色覆盖 AntD 主色、成功色、信息色、错误色
- 统一 `a-card`、`a-tabs`、`a-table`、`a-input`、`a-select`、`a-drawer`、`a-modal` 的深色表面变量
- 去掉现有只覆盖少量根变量的做法

在 `frontend/src/App.vue` 中保持全局样式引入顺序稳定，确保 `global.less` 和 `antd-override.less` 继续作为唯一入口。

**Step 2: Run test to verify it passes**

Run: `node --test "frontend/test/global-ui-refresh-surface.test.ts"`
Expected: PASS，说明全局 token 与主题入口已经到位。

### Task 3: 统一默认布局、公共页头与筛选条

**Files:**
- Modify: `frontend/src/components/layout/DefaultLayout.vue`
- Modify: `frontend/src/components/common/AppPageHeader.vue`
- Modify: `frontend/src/components/common/AppFilterBar.vue`
- Test: `frontend/test/global-ui-refresh-surface.test.ts`

**Step 1: Write minimal implementation**

重做 `frontend/src/components/layout/DefaultLayout.vue`：

- 顶部导航从“普通 dark menu”改为玻璃质感头部
- Logo、导航项、登录按钮、语言切换和用户菜单改成同一品牌语言
- 增加背景层类名，例如：

```vue
<a-layout class="default-layout shell-backdrop">
  <a-layout-header class="header header-chrome">
```

- 为导航项引入 `nav-pill` / `nav-pill-active` 语义类名，而不是只依赖 AntD 默认选中态
- 移动端 `a-drawer` 也使用同一深色表面，不保留默认白抽屉
- 页脚改为品牌化信息区，而不是简单链接行

重做 `frontend/src/components/common/AppPageHeader.vue`：

- 标题、副标题、操作区统一为可复用页头模块
- 增加横向装饰、kicker、标题层级和响应式留白
- 保留原有 props API，避免大范围破坏调用方

重做 `frontend/src/components/common/AppFilterBar.vue`：

- 从普通白色工具栏改成深色悬浮控制条
- 统一输入框、筛选器、按钮的对齐与间距
- 保留插槽 API，不改页面调用结构

**Step 2: Run test to verify it passes**

Run: `node --test "frontend/test/global-ui-refresh-surface.test.ts"`
Expected: PASS，公共壳层类名和统一组件结构可被测试命中。

### Task 4: 统一首页、工具页与工作台页面气质

**Files:**
- Modify: `frontend/src/views/home/index.vue`
- Modify: `frontend/src/views/tools/List.vue`
- Modify: `frontend/src/views/tools/Detail.vue`
- Modify: `frontend/src/views/workflow/index.vue`
- Modify: `frontend/src/components/workflow/WorkflowStepSidebar.vue`
- Modify: `frontend/src/components/workflow/WorkflowRunPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowArtifactPanel.vue`
- Test: `frontend/test/global-ui-refresh-surface.test.ts`

**Step 1: Write the failing test**

先在 `frontend/test/global-ui-refresh-surface.test.ts` 追加断言：

- `home/index.vue` 保留深色科研门面，但新增与全局 token 一致的面板类名
- `tools/List.vue` 使用统一结果摘要、工具卡片和工作台入口面板类名
- `workflow/index.vue` 使用统一的三栏面板语义，而不是局部独立视觉

示例断言：

```ts
assert.equal(homeSource.includes('hero-observatory') || homeSource.includes('panel-surface'), true)
assert.equal(toolListSource.includes('workflow-entry-card'), true)
assert.equal(workflowSource.includes('workflow-layout'), true)
```

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/global-ui-refresh-surface.test.ts"`
Expected: FAIL，因为页面还没有映射到新的统一表面类和气质。

**Step 3: Write minimal implementation**

首页 `frontend/src/views/home/index.vue`：

- 保留现有 Hero 结构，但把配色、面板、文字层级与新的全局 token 对齐
- Features / CTA / workflow section 统一到同一表面体系

工具列表 `frontend/src/views/tools/List.vue`：

- 将工作台入口卡片升级为品牌化“工作台入口面板”
- 统一 tab、筛选条、结果摘要、工具卡片 hover / focus / empty state
- 保持现有数据流和筛选逻辑，不改 store API

工具详情 `frontend/src/views/tools/Detail.vue`：

- 统一参数表单、任务名称输入、提交区、说明面板样式
- 与任务详情页保持一致的 panel spacing 和 header hierarchy

工作台 `frontend/src/views/workflow/index.vue` 及三块面板：

- 左列、主运行区、右侧产物区改成统一实验台式 panel
- 强化选中态、推荐态、运行态、空态
- 不改工作流行为，只统一视觉和层级

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/global-ui-refresh-surface.test.ts"`
Expected: PASS

### Task 5: 统一任务页为运行控制台视觉

**Files:**
- Modify: `frontend/src/views/tasks/List.vue`
- Modify: `frontend/src/views/tasks/Detail.vue`
- Test: `frontend/test/global-ui-refresh-surface.test.ts`

**Step 1: Write the failing test**

在 `frontend/test/global-ui-refresh-surface.test.ts` 中增加断言：

- `tasks/List.vue` 使用统一控制台卡片 / 监控面板类名
- `tasks/Detail.vue` 使用统一详情面板壳层和状态区域类名

示例：

```ts
assert.equal(listSource.includes('monitor-panel'), true)
assert.equal(listSource.includes('task-card'), true)
assert.equal(detailSource.includes('task-detail-page') || detailSource.includes('detail-panel'), true)
```

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/global-ui-refresh-surface.test.ts"`
Expected: FAIL，因为任务页仍停留在旧卡片和旧层级。

**Step 3: Write minimal implementation**

任务列表 `frontend/src/views/tasks/List.vue`：

- 保留现有三标签、筛选和实时监控结构
- 将任务卡片、监控面板、状态标签、进度圈样式统一到新的控制台视觉
- 提高信息密度但保持点击区域和移动端可用性

任务详情 `frontend/src/views/tasks/Detail.vue`：

- 重做标题区、状态区、信息网格、日志/结果/参数面板的视觉层级
- 保持现有 WebSocket 和任务更新逻辑不变

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/global-ui-refresh-surface.test.ts"`
Expected: PASS

### Task 6: 统一管理后台壳层与高密度内容区

**Files:**
- Modify: `frontend/src/views/admin/index.vue`
- Modify: `frontend/src/views/admin/Dashboard.vue`
- Modify: `frontend/src/views/admin/Tools.vue`
- Modify: `frontend/src/views/admin/Tasks.vue`
- Test: `frontend/test/global-ui-refresh-surface.test.ts`

**Step 1: Write the failing test**

在 `frontend/test/global-ui-refresh-surface.test.ts` 中追加断言：

- `frontend/src/views/admin/index.vue` 采用新的管理端 shell 类名，例如 `admin-shell`、`admin-chrome`
- `Dashboard.vue`、`Tools.vue`、`Tasks.vue` 继续复用 `AppPageHeader` 和 `AppFilterBar`
- 管理端表格和统计卡片改为统一 panel 风格，而不是裸 `a-card`

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/global-ui-refresh-surface.test.ts"`
Expected: FAIL，因为管理端还保留默认后台壳层。

**Step 3: Write minimal implementation**

管理端壳层 `frontend/src/views/admin/index.vue`：

- 重做侧边栏、顶部栏、面包屑、用户菜单和内容背景
- 让管理端和用户端共享同一品牌色、边框、阴影和字体体系
- 只修改实际生效的 `views/admin/index.vue`，不触碰未接线路由的 `components/layout/AdminLayout.vue`

管理端核心内容页：

- `Dashboard.vue`：统计卡、表格面板、标题区统一样式
- `Tools.vue`：表格容器、筛选栏、导入弹窗统一主题
- `Tasks.vue`：统计卡、筛选栏、表格、Drawer 统一深色表面

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/global-ui-refresh-surface.test.ts"`
Expected: PASS

### Task 7: 做最终验证并修正构建问题

**Files:**
- Test: `frontend/test/global-ui-refresh-surface.test.ts`
- Test: `frontend/`

**Step 1: Run focused frontend surface tests**

Run: `node --test "frontend/test/global-ui-refresh-surface.test.ts"`
Expected: PASS

**Step 2: Run existing frontend regression test**

Run: `node --test "frontend/test/task-name-surface.test.ts"`
Expected: PASS，任务命名相关表面行为不被 UI 改造破坏。

**Step 3: Run production build**

Run: `npm run build`

Workdir: `frontend/`

Expected: PASS，Vite 构建成功，无类型错误和样式导入错误。

**Step 4: Fix any build or style regression with minimal edits**

如果构建报错，只修：

- 类名引用错误
- Less 变量缺失
- 组件模板中遗留的旧结构引用

不要在这一阶段追加新视觉需求，保持 YAGNI。
