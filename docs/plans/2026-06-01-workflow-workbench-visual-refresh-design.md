# 工作台产物与视觉统一设计

## 目标

修复工具工作台中“我的产物”组件的任务卡排版问题，并将整个 `/workflow` 页面统一成更完整的实验工作台视觉体系。

本次改动要同时满足两个目标：

- `任务展示可读`
  - 任务节点优先展示任务名
  - 任务 ID 只作为次信息显示短 ID
  - 避免长 UUID 被逐字符换行，导致卡片变成竖向长条
- `工作台整体更美观`
  - 左栏分组、中栏运行面板、右栏我的产物，统一成同一套浅色实验甲板风格
  - 保留现有三栏信息结构和复用产物能力，不做激进重构

## 背景

当前工作台已经具备：

- 分组驱动的工具工作台
- 参数里的四级产物复用链路
- 右侧按 `工具分组 -> 工具 -> 任务 -> 任务产物` 浏览产物

但仍然存在两个明显问题。

### 1. 任务卡的长 ID 会被竖着拆开

在 [frontend/src/components/workflow/WorkflowArtifactPanel.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/components/workflow/WorkflowArtifactPanel.vue) 中，任务卡当前把 `#taskId` 当主标题显示，并且样式对 `artifact-task-id` 使用了：

- `display: block`
- `overflow-wrap: anywhere`

对于 UUID 这样的长字符串，这会导致浏览器在任意字符之间断行，最终形成“一字一行”的竖排效果，卡片高度被无限拉长。

### 2. 工作台三栏视觉语义不统一

当前三栏可用，但像三块不同页面拼接：

- 左栏 [WorkflowStepSidebar.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/components/workflow/WorkflowStepSidebar.vue) 更像后台菜单列表
- 中栏 [WorkflowRunPanel.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/components/workflow/WorkflowRunPanel.vue) 更像标准管理表单
- 右栏 [WorkflowArtifactPanel.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/components/workflow/WorkflowArtifactPanel.vue) 是另一套树卡布局

这会让 `/workflow` 缺少“统一工作台”的整体感。

## 核心设计决策

### 1. 任务节点改为“任务名主标题，短 ID 次信息”

这是本次最核心的可用性决策。

任务节点的新层级为：

- 主标题：`任务名`
- 次信息：`#短ID · 最近产物时间 · 产物数`
- 操作区：`定位路径 / 查看任务`

如果任务没有名称：

1. 优先使用后端已经生成的默认任务名
2. 若产物接口没有带出名称，则回退为 `任务 #短ID`

这样用户第一眼看到的是“这个任务是什么”，而不是冗长 UUID。

### 2. 长 ID 不再作为主视觉，不允许逐字符断裂

完整任务 ID 不再占据主标题位置。

短 ID 推荐规则：

- 使用前 8 位，例如 `#c708fb51`

完整 ID 如需保留，只作为：

- tooltip
- 调试信息
- 或详细页跳转后的补充信息

在任务卡主区域中，不再允许 `overflow-wrap: anywhere` 作用于任务 ID。

### 3. 产物接口补 `task_name`

目前前端 [ArtifactFile](/data/zhouyc/cpumodel_sciminer/frontend/src/types/models.d.ts:408) 只有：

- `task_id`
- `tool_id`
- `tool_name`
- `tool_slug`

但没有 `task_name`。

为了真正实现“任务名优先”，本次需要对后端产物接口做一个最小增量：

- [backend/app/schemas/files.py](/data/zhouyc/cpumodel_sciminer/backend/app/schemas/files.py)
  - `ArtifactFileResponse` 新增 `task_name: Optional[str]`
- [backend/app/api/v1/files.py](/data/zhouyc/cpumodel_sciminer/backend/app/api/v1/files.py)
  - 组装 `/files/artifacts` 返回时写入 `task.name`

这是一个非常小但高价值的字段补充，能避免前端再额外发任务详情请求。

### 4. 三栏统一为“浅色实验甲板”

这次不做深色重控制台，而是延续首页中段已经建立起来的浅色实验甲板语言：

- 轻渐变背景
- 干净边框
- 柔和阴影
- 明确的区块分层
- 稳定的状态标签和操作按钮

原因：

- 与当前首页中段的视觉语言一致
- 风险低于整站深色重绘
- 更适合长时间阅读表单和产物列表

## 组件级设计

### A. 我的产物面板

#### 任务卡结构

任务卡将从“ID 盒子”改为“研究记录卡”：

- 第一行
  - 左侧：任务名
  - 右侧：产物数 / 状态标签 / 操作入口
- 第二行
  - 短 ID
  - 最近产物时间
  - 来源工具（可保留在 meta 区）
- 展开区
  - 产物列表
  - “还有 N 个产物”提示

#### 排版规则

- `任务名`
  - 允许 1 到 2 行自然截断
- `短 ID`
  - 单行展示
  - `white-space: nowrap`
  - 不允许 `overflow-wrap: anywhere`
- `时间与来源`
  - 做成紧凑 meta 粒度，不再占主标题位置

#### 任务树层级

原有四级结构保持不变：

- 工具分组
- 工具
- 任务
- 任务产物

只是任务节点会从“技术信息优先”变成“业务语义优先”。

### B. 左栏分组导航

左栏不是菜单，而是“研究分组导航”。

优化点：

- 激活组增加更清晰的高亮条和轻底色
- 分组卡更像研究主题卡，而不是普通列表项
- `工具数 / 推荐数` 统一成同风格胶囊标签

### C. 中栏运行面板

中栏不重构逻辑，只重新组织视觉层级：

1. 当前分组横幅
2. 工具选择条
3. 当前工具摘要
4. 参数表单
5. 提交动作底栏

目标是让它看起来像一个完整的“实验参数台”，而不是散落的表单块。

### D. 页面级工作台壳层

[frontend/src/views/workflow/index.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/views/workflow/index.vue) 的页面级壳层会继续保留三栏，但统一以下规则：

- 同一套背景纹理
- 同一套列间距
- 同一套卡片边框与阴影
- sticky 行为保留，但滚动容器更干净

## 数据流

### 后端到前端

`/api/v1/files/artifacts` 增加 `task_name`

前端链路：

1. [files.ts](/data/zhouyc/cpumodel_sciminer/frontend/src/types/models.d.ts) 的 `ArtifactFile` 增加 `task_name?: string`
2. [artifact-hierarchy.ts](/data/zhouyc/cpumodel_sciminer/frontend/src/workflow/artifact-hierarchy.ts)
   - `WorkflowArtifactTaskNode.taskName` 真正写入数据
3. [WorkflowArtifactPanel.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/components/workflow/WorkflowArtifactPanel.vue)
   - UI 优先渲染 `taskName`

### 回退逻辑

如果某条产物没有 `task_name`：

- 用短 ID 补标题
- 不影响展开、定位路径和查看任务

这样即使历史数据不完整，也不会出现空标题。

## 视觉方向

### 总方向

`浅色实验工作台`

关键词：

- 精准
- 稳定
- 分层清楚
- 专业但不沉重

### 具体风格

- 背景：淡蓝灰渐变 + 微弱网格/雾化纹理
- 卡片：轻玻璃感但不高透明
- 标题：中高字重，少花样
- 状态：tag 颜色更克制
- 动效：只保留 hover 抬升和细微过渡，不做夸张动效

## 测试策略

### 后端测试

优先复用 [test/test_file_artifacts_api.py](/data/zhouyc/cpumodel_sciminer/test/test_file_artifacts_api.py)：

- 新增断言 `/files/artifacts` 返回 `task_name`
- 验证有名任务与无名任务都能正常返回

### 前端测试

建议覆盖两类：

#### 1. 数据与结构

复用 [frontend/test/workflow-artifact-hierarchy.test.ts](/data/zhouyc/cpumodel_sciminer/frontend/test/workflow-artifact-hierarchy.test.ts)

- 增加 `task_name -> taskName` 的层级传递断言

#### 2. 表面样式语义

新增一个面板/工作台表面测试，锁定：

- 任务节点优先展示任务名
- 短 ID 为次信息
- 不再对任务 ID 使用 `overflow-wrap: anywhere`
- 工作台三栏使用统一的壳层类名和视觉区块类名

### 构建验证

- `pytest test/test_file_artifacts_api.py -q`
- `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`
- `node --test "frontend/test/<workflow-workbench-surface>.ts"`
- `npm run build`（`frontend/`）

## 风险与控制

### 风险 1：历史产物没有任务名

控制方式：

- 后端返回 `task_name` 可为空
- 前端做好回退标题逻辑

### 风险 2：工作台样式优化波及现有交互

控制方式：

- 不改三栏职责与核心数据流
- 先锁定表面测试，再做最小样式重绘

### 风险 3：移动端布局被桌面美化破坏

控制方式：

- 保留现有响应式断点策略
- 所有新样式都在窄屏下回退为纵向堆叠

## 非目标

这次不会做：

- 改动工作台信息架构
- 改成深色整页控制台
- 重新设计参数复用选择器逻辑
- 引入新的后端接口，只做 `/files/artifacts` 字段补充

