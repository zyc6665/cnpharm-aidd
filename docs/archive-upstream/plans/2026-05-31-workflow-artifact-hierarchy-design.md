# 工作台产物四级层级设计

## 目标

把工作台中的产物浏览与产物复用统一为稳定的四级层级：

- `工具分组 -> 工具 -> 任务 -> 任务产物`

第一版覆盖两个入口：

- 参数表单中的“选择我的产物”
- 工作台右侧“产物面板”

目标不是新增后端能力，而是在现有工作台分组和产物数据之上，前端稳定派生出一致的层级结构。

## 背景与现状

当前工作台产物链路已经有可复用能力，但展示层级不完整：

### 1. 参数选择器只有两级

当前 [frontend/src/components/tools/ArtifactFilePicker.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/components/tools/ArtifactFilePicker.vue) 只做了：

- `任务 -> 产物`

并且它依赖 [frontend/src/components/tools/artifact-selection.ts](/data/zhouyc/cpumodel_sciminer/frontend/src/components/tools/artifact-selection.ts) 中的 `groupCompatibleArtifactsByTask(...)`，这意味着：

- 看不到任务属于哪个工具分组
- 看不到任务属于哪个工具
- 当历史任务越来越多时，任务下拉会越来越难定位

### 2. 右侧产物面板是另一套分组逻辑

[frontend/src/components/workflow/WorkflowArtifactPanel.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/components/workflow/WorkflowArtifactPanel.vue) 当前做的是：

- 当前分组下若干任务卡片
- 最近任务若干任务卡片

它在组件内部自写了一套 `groupArtifactsByTask(...)`，和参数选择器不是同一个分组模型。

结果就是：

- 左侧参数复用和右侧产物浏览的认知路径不一致
- 同一份产物在两边的归属方式不同
- 代码层面也违反 `DRY`

### 3. 工作台已有“工具分组”和“工具”数据，但没有串到产物层

工作台页 [frontend/src/views/workflow/index.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/views/workflow/index.vue) 已经拿到了：

- `WorkbenchGroup[]`
- `group.tools[]`
- `ArtifactFile[]`

也就是说，当前缺的不是数据，而是统一的前端派生模型。

## 核心设计决策

### 1. 采用纯前端派生，不改后端接口

第一版不改产物接口，也不改任务模型，不让后端返回“所属工作台分组”。

原因：

- 当前前端已经同时持有 `groups + artifacts`
- 用户已经确认归属规则可以按前端分组顺序判定
- 这个需求本质是工作台内的展示和选择层级，不值得先引入后端耦合

因此本次采用：

- 前端共享派生器
- 两个组件共同消费

### 2. 工具分组归属按“首个匹配分组”判定

用户已确认：

- 如果某工具同时属于多个工作台分组
- 只归到“当前工作台分组列表顺序”中的首个匹配分组

这条规则是本次层级派生的基础。

派生方式：

1. 遍历工作台分组列表顺序
2. 为每个工具建立 `toolSlug -> primaryGroupId`
3. 某任务和其产物一律归到该 `primaryGroupId`

这样可以避免：

- 同一个任务在多个分组中重复显示
- 同一个产物在多个分组中重复出现

### 3. 统一抽象为共享四级树

新增一个前端共享派生模块，统一产出：

- `groupNodes[]`
- `groupNode.tools[]`
- `toolNode.tasks[]`
- `taskNode.artifacts[]`

这棵树是参数选择器和产物面板的唯一数据源。

这样可以：

- 避免一边按任务分组、一边按卡片手工拼装
- 保持两个入口的归属规则和排序规则完全一致
- 让后续增加搜索、折叠、默认定位时不需要改两份逻辑

### 4. 参数选择器改成四级级联，而不是一个巨型下拉

参数复用入口不做复杂 Tree，也不做单个超长 `Select`。

交互保持简单：

- 先选 `工具分组`
- 再选 `工具`
- 再选 `任务`
- 最后选 `任务产物`

原因：

- 更符合用户认知路径
- 比把所有信息塞进同一个选项 label 更清楚
- 对移动端和长列表更友好

### 5. 产物面板按同一棵树渲染两个视角

产物面板保留两个视角，但都基于同一棵四级树：

- `当前工作台分组视角`
- `全局最近产物视角`

区别只在过滤范围，不在层级模型。

## 数据模型设计

建议新增共享类型模块，例如：

- `frontend/src/workflow/artifact-hierarchy.ts`

或：

- `frontend/src/components/tools/artifact-hierarchy.ts`

推荐放在 `frontend/src/workflow/`，因为它同时服务工作台产物面板和工作台内的工具参数复用。

建议类型：

```ts
interface WorkflowArtifactGroupNode {
  groupId: string
  groupName: string
  groupSlug: string
  tools: WorkflowArtifactToolNode[]
}

interface WorkflowArtifactToolNode {
  toolId?: string
  toolSlug: string
  toolName: string
  tasks: WorkflowArtifactTaskNode[]
}

interface WorkflowArtifactTaskNode {
  taskId: string
  taskName?: string
  latestCreatedAt: string
  artifacts: ArtifactFile[]
}
```

核心输入：

```ts
buildWorkflowArtifactHierarchy({
  groups,
  artifacts,
  accept,
  scope
})
```

其中：

- `groups` 来自工作台分组
- `artifacts` 来自产物 store
- `accept` 只在参数选择器场景使用
- `scope` 控制是“当前工作台分组”还是“全局最近”

## 派生规则

### 1. 主分组映射

先按工作台分组顺序建立：

- `Map<toolSlug, groupMeta>`

规则：

- 同一个 `toolSlug` 首次命中哪个分组，就固定归到哪个分组
- 后续分组命中忽略

### 2. 产物过滤

在进入四级树之前先过滤：

- 排除噪音文件
- 按 `accept` 过滤不兼容产物
- 过滤掉当前工具自身不允许复用的链路（沿用现有 `currentToolId/currentToolSlug` 逻辑）

这一步复用或迁移 [artifact-selection.ts](/data/zhouyc/cpumodel_sciminer/frontend/src/components/tools/artifact-selection.ts) 中已有的：

- `isNoiseArtifact`
- `isArtifactCompatibleWithAccept`
- `filterCompatibleArtifacts`

### 3. 任务归属

每个任务根据其产物中的：

- `artifact.tool_slug`

映射到主分组，再映射到具体工具节点。

一个任务节点下保留：

- 任务 ID
- 任务名（如果产物对象里没有，允许为空）
- 最新产物时间
- 该任务下所有有效产物

### 4. 排序规则

排序规则统一固定：

- 分组：按工作台现有顺序
- 工具：按分组内工具原始顺序
- 任务：按最新产物时间倒序
- 产物：按创建时间倒序

## 参数选择器设计

修改 [frontend/src/components/tools/ArtifactFilePicker.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/components/tools/ArtifactFilePicker.vue)：

### 状态从 1 个任务下拉扩展为 3 个层级选择 + 1 个产物选择

新增本地状态：

- `selectedGroupId`
- `selectedToolSlug`
- `selectedTaskId`

行为：

1. 选分组后，工具列表联动收缩
2. 选工具后，任务列表联动收缩
3. 选任务后，产物列表联动收缩
4. 选中产物后，照旧向外触发 `update:selectedArtifact`

### 自动回填

如果外部传入了 `selectedArtifact`：

- 先在共享四级树中反查所属 `group/tool/task`
- 自动回填三级选择器

### 默认定位

对于工作台里的运行面板，可以额外支持：

- 优先默认定位到当前已选工作台分组
- 再优先定位到当前已选工具

这样能减少用户点击次数。

## 产物面板设计

修改 [frontend/src/components/workflow/WorkflowArtifactPanel.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/components/workflow/WorkflowArtifactPanel.vue)：

### 统一改成四级展示

展示结构：

- 分组区块
- 工具折叠段
- 任务卡片
- 任务卡片内的产物列表

建议不是直接用 Ant Design Tree，而是继续用当前卡片体系：

- 分组标题更清晰
- 工具作为二级 section
- 任务保留“查看任务”操作
- 产物保留文件名和必要元信息

### 两个视角的边界

当前工作台分组视角：

- 只展示当前激活分组对应的树分支

全局最近产物视角：

- 展示所有分组
- 如果某工具已不属于任何工作台分组，则放入虚拟分组：
  - `未分组工具`

这样不会丢失历史产物。

## 边界情况

### 1. 工具命中多个分组

按首个匹配分组归属，只显示一次。

### 2. 工具已不在任何分组

在“全局最近产物视角”挂到虚拟分组 `未分组工具`。

第一版不把它混进当前分组视角。

### 3. `accept` 过滤后产生空节点

任何空节点都裁掉：

- 没产物的任务不显示
- 没任务的工具不显示
- 没工具的分组不显示

### 4. 已选产物不再可用

如果当前已选产物因刷新后不再存在或不再兼容：

- 清空当前选择
- 保持当前层级定位尽量不变

## 测试策略

### 1. 纯函数测试

为新的共享派生器增加测试，覆盖：

- 按分组顺序建立主分组归属
- 多分组命中时只归首个分组
- `accept` 过滤后空节点裁剪正确
- 虚拟分组 `未分组工具` 的挂载行为正确

### 2. 参数选择器表面测试

覆盖：

- 出现 `分组 -> 工具 -> 任务 -> 产物` 四级链路
- 已选产物可自动回填
- 分组切换会重置下层选择

### 3. 产物面板表面测试

覆盖：

- 当前分组视角按 `分组 -> 工具 -> 任务 -> 产物` 展示
- 全局最近视角也沿用同一结构

### 4. 回归测试

必须确保以下功能不受影响：

- 任务命名
- 工作台工具运行
- 产物刷新
- 任务详情跳转

## 非目标

第一版不做以下内容：

- 后端返回主分组字段
- 数据库持久化“任务所属工作台分组”
- 为分组增加独立优先级字段
- 产物全文搜索
- 拖拽排序或复杂树形交互

## 推荐实现路径

推荐顺序：

1. 先抽共享四级树派生器和纯函数测试
2. 再改参数选择器到四级级联
3. 最后改右侧产物面板消费同一棵树

这样可以把风险控制在最小范围，并且每一步都可独立验证。
