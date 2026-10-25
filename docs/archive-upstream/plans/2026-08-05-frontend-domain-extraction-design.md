# Frontend Domain Extraction Design

## 背景

当前前端已经是 `Vue 3 + Vite + TypeScript`，因此本轮不是把 JavaScript 改成 TypeScript，而是把散落在 Vue 页面里的业务规则抽成框架无关 TypeScript 模块。目标是继续保留 Vue3 作为 UI Adapter，同时让任务、Tool Package、项目工作台和 Workflow 的核心规则变成可复用、可测试、未来可迁移到 React 的深模块。

当前项目已有一部分良好基础：`frontend/src/workflow/` 已经承载较多框架无关逻辑，`frontend/src/utils/` 也有少量工具函数。但仍有一些重页面把状态、权限、展示规则和路由规则混在 `.vue` 文件中，例如：

- `frontend/src/views/tasks/List.vue` 约 971 行，包含任务过滤、状态展示、权限判断、项目上下文和 Artifact 谱系跳转。
- `frontend/src/views/tasks/Detail.vue` 约 938 行，包含任务详情、日志、输出渲染和操作规则。
- `frontend/src/views/admin/ToolPackages.vue` 约 468 行，包含 manifest 解析、校验、发布状态和 Artifact 契约展示。
- `frontend/src/views/workflow/index.vue` 约 695 行，但已有 `frontend/src/workflow/` 可继续深化。

## 目标

- Vue 组件只负责渲染、事件绑定、生命周期和 UI 状态。
- 业务规则进入框架无关 TypeScript 模块，不依赖 `vue`、`pinia`、`vue-router` 或 Ant Design Vue。
- 每个 domain 模块以小 Interface 暴露较深 Implementation，让页面调用简单函数而不是复制业务判断。
- 对抽出的规则补 Vitest 单测，避免权限、状态、Artifact 链路或 Workflow 行为回退。
- 不改变后端接口、不改视觉设计、不重写页面。

## 模块设计

### `frontend/src/domain/tasks/`

任务中心是第一批抽离对象。该模块承载任务状态、任务列表过滤、权限判断和项目上下文路径规则。

建议文件：

```text
frontend/src/domain/tasks/status.ts
frontend/src/domain/tasks/permissions.ts
frontend/src/domain/tasks/listing.ts
frontend/src/domain/tasks/navigation.ts
frontend/src/domain/tasks/index.ts
```

Interface 示例：

```ts
getTaskStatusColor(status)
getTaskProgressStatus(status)
getTaskProgressColor(status)
isRunningTask(task)
isHistoryTask(task)
filterTasksForTab(tasks, tab)
filterTasksByKeyword(tasks, keyword)
paginateTasks(tasks, page, pageSize)
canOperateTask(task, actor)
canCancelTask(task, actor)
canRetryTask(task, actor)
canDeleteTask(task, actor)
getTaskProjectContextLabel(task, context)
getTaskArtifactLineagePath(task)
```

Vue 页面保留 i18n 文案调用，但状态码、颜色、权限、过滤和路径不再内联在页面中。

### `frontend/src/domain/tool-packages/`

第二批抽离 Tool Package 的 manifest 和发布规则。该模块应该处理当前版本、validation errors、签名状态、发布 readiness、Artifact 输入输出槽、variant 摘要和 manifest 格式化。

Vue 页面只负责展示 Drawer、表格和按钮；发布可用性说明、校验文案来源和 Artifact slot 提取由 domain 模块提供。

### `frontend/src/domain/projects/`

第三批抽离项目工作台导航、资源摘要、Artifact 标签和下载 URL 包装规则。项目页面应减少直接拼路由和直接格式化 Artifact 业务标签。

### `frontend/src/workflow/` 深化

第四批不新建平行目录，继续深化已有 `frontend/src/workflow/`。目标是把 Vue store/composable 里的画布运行状态、预检、Artifact 绑定和节点状态规则进一步收敛到现有 workflow 深模块中。

## 数据流

页面读取 Pinia store、route 和 API 返回数据后，组装成简单 domain input：

```text
Vue page/store state -> domain pure functions -> UI props/render decisions
```

domain 模块不读取浏览器存储、不发 API、不访问 router、不调用 message。这样测试可以直接构造输入并断言输出。

## 错误处理

- API 错误仍由现有请求层和页面生命周期处理。
- domain 模块不吞异常；对不完整数据返回保守结果，例如无项目上下文时显示短 ID，无版本时返回不能发布。
- 权限规则默认拒绝，状态规则默认稳定降级。

## 测试策略

- 每批先写 domain 单测，再迁移页面调用。
- 保留已有页面结构测试，必要时更新为检查页面调用 domain 模块。
- 第一批至少覆盖：任务状态展示、运行/历史过滤、关键字过滤、分页、项目角色权限、owner/admin 权限、Artifact 谱系路径。
- 每批运行聚焦前端测试和 `npm run build`。

## 分批实施

1. 任务中心 domain 抽离：`List.vue` 权限、状态、过滤和导航规则迁出。
2. Tool Package domain 抽离：manifest、validation、publish readiness 和 Artifact slot 规则迁出。
3. Project Workspace domain 抽离：项目导航、摘要和 Artifact 标签规则迁出。
4. Workflow 深化整理：继续把 Vue store/composable 中的运行规则归入 `frontend/src/workflow/`。

每批完成后执行 review、测试和单独提交。
