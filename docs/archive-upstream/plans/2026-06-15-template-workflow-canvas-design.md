# 模板式工作流节点编排设计

## 背景

当前平台已经具备工具管理、任务执行、文件产物、AIDD 工作流和工作台分组能力。现有 `/workflow` 页面采用“步骤侧栏 + 运行面板 + 产物面板”的三栏结构，能够完成工具选择、参数填写、任务运行和产物绑定，但流程关系不够直观。

目标是先实现“模板式节点编排”：用户选择预设流程模板后，以节点和连线展示工具流程；点击节点配置参数、绑定输入、运行任务、查看产物。后续再升级为自由拖拽编排画布。

参考图片中的交互形态：左侧为组件/步骤列表，中间为节点画布，右侧为节点参数面板，节点之间通过连线表达输入输出依赖。

## 设计目标

1. 第一版支持固定模板，不支持用户新增、删除、拖拽节点。
2. 用节点图替换或增强当前手动工作流的流程表达。
3. 复用现有工具、任务、产物、工作台分组和 AIDD workflow 类型。
4. 点击节点后在右侧配置工具、参数、输入产物和运行动作。
5. 节点状态跟随任务状态变化，已完成节点产物可作为下游输入。
6. 数据结构预留 `nodes`、`edges`、`position`，便于后续升级自由拖拽。

## 非目标

第一版不做以下能力：

- 任意拖拽节点。
- 用户自定义连线。
- 循环、条件分支、并发调度编排。
- 一键自动执行完整 DAG。
- 后端持久化自定义模板。
- 多人实时协同编辑。

## 现有代码基础

可复用模块：

- `frontend/src/views/workflow/index.vue`：现有工作流页面入口。
- `frontend/src/stores/workflow.ts`：工作流会话、工具选择、参数草稿和任务记录。
- `frontend/src/workflow/artifact-types.ts`：步骤状态、语义产物类型、任务引用类型。
- `frontend/src/workflow/aidd-catalog.ts`：AIDD 步骤定义，可扩展为模板来源。
- `frontend/src/workflow/tool-bindings.ts`：工具与流程步骤的绑定关系。
- `frontend/src/components/workflow/WorkflowRunPanel.vue`：工具运行和参数表单能力。
- `frontend/src/components/workflow/WorkflowArtifactPanel.vue`：产物选择和绑定能力。
- `frontend/src/components/workflow/WorkflowStepSidebar.vue`：步骤导航能力。
- `frontend/src/stores/tools.ts`：工作台分组和工具选项获取。
- `frontend/src/stores/artifacts.ts`：任务产物获取。

后端第一版可继续复用现有接口：

- `/api/v1/tools/workbench-groups`
- `/api/v1/tools`
- `/api/v1/tasks`
- `/api/v1/files/artifacts`

## 第一版信息架构

页面仍放在 `/workflow`，建议将 `manual` 模式升级为“模板编排”。

布局：

- 顶部工具条：模板选择、当前流程状态、保存草稿、刷新、运行当前节点。
- 左侧步骤栏：展示模板节点分组、节点状态和错误提示。
- 中间画布：展示固定节点、连线、状态徽标、输入输出标记。
- 右侧参数面板：展示当前节点详情、工具选择、参数表单、输入产物绑定、运行结果。
- 底部可选区域：运行日志、最近任务、失败原因。

第一版节点不可拖动，但允许点击、选中、缩放和查看。

## 模板与节点模型

第一版前端内置模板，后续可迁移到后端。

```ts
export type WorkflowTemplateKind = 'aidd' | 'docking' | 'pocket' | 'screening'

export interface WorkflowTemplate {
  id: string
  kind: WorkflowTemplateKind
  nameKey: string
  descriptionKey?: string
  nodes: WorkflowCanvasNode[]
  edges: WorkflowCanvasEdge[]
}

export interface WorkflowCanvasNode {
  id: string
  type: 'input' | 'tool' | 'artifact' | 'result'
  stepKey?: WorkflowStepKey
  toolSlugs?: string[]
  recommendedToolSlug?: string
  titleKey: string
  descriptionKey?: string
  position: { x: number; y: number }
  requiredInputTypes?: WorkflowArtifactSemanticType[]
  producedOutputTypes?: WorkflowArtifactSemanticType[]
}

export interface WorkflowCanvasEdge {
  id: string
  source: string
  target: string
  artifactType?: WorkflowArtifactSemanticType
  labelKey?: string
}
```

说明：

- `position` 第一版由模板固定，用于后续自由画布直接复用。
- `toolSlugs` 支持一个节点绑定多个可选工具。
- `requiredInputTypes` 和 `producedOutputTypes` 用于自动推荐上游产物。
- `artifactType` 用于连线标签和下游输入匹配。

## 状态模型

扩展 `useWorkflowStore`，新增模板和节点状态：

```ts
interface WorkflowCanvasSession {
  templateId: string
  activeNodeId: string | null
  selectedToolByNode: Record<string, string>
  nodeFormDrafts: Record<string, Record<string, unknown>>
  taskByNode: Record<string, WorkflowTaskRef>
  artifactBindingsByNode: Record<string, Record<string, string>>
  nodeStateById: Record<string, WorkflowStepRecord>
}
```

兼容策略：

- 现有 `selectedToolByGroup`、`toolFormDrafts`、`taskByTool` 暂不删除。
- 新编排器先使用 `nodeId` 维度记录状态。
- 需要兼容现有运行面板时，可从 `node.toolSlug` 映射到旧字段。

## 节点状态计算

节点状态由任务、输入和工具选择共同决定：

- `idle`：未选择工具或未准备输入。
- `needs_tool_selection`：节点有多个工具但尚未选择。
- `ready`：工具已选择，必需输入已绑定。
- `running`：节点关联任务正在运行。
- `completed`：节点关联任务成功完成。
- `failed`：节点关联任务失败。
- `invalidated`：上游产物更新后，下游已完成结果需要重新运行。

当上游节点重新运行成功后：

1. 找到所有下游节点。
2. 若下游节点已有任务结果，标记 `invalidated`。
3. 清理或提示更新下游输入绑定。

## 用户流程

### 进入页面

1. 用户进入 `/workflow`。
2. 默认选择 AIDD 模板。
3. 系统加载工作台分组、工具列表和最近产物。
4. 画布展示模板节点和连线。

### 配置节点

1. 用户点击某个工具节点。
2. 右侧面板展示节点名称、可选工具、必需输入、参数表单。
3. 系统根据 `requiredInputTypes` 推荐上游节点最新产物。
4. 用户确认参数和输入。

### 运行节点

1. 用户点击“运行当前节点”。
2. 前端调用现有 `/api/v1/tasks` 创建任务。
3. `taskByNode[nodeId]` 记录任务引用。
4. 节点进入 `running`。
5. 任务完成后，刷新产物并更新节点状态。

### 查看结果

1. 点击已完成节点。
2. 右侧展示任务摘要、输出文件、可视化组件和日志入口。
3. 下游节点输入区域展示可继承的产物。

## AIDD 模板第一版

建议默认模板节点：

1. 蛋白结构输入：`input`，产出 `protein_structure`。
2. 口袋探索：`tool`，绑定 `pocket-explorer`，产出 `pocket_structure`。
3. 分子生成/虚拟筛选：`tool`，绑定 `gcdm-pocket-generation`、`targetdiff-service`，产出 `generated_ligand`。
4. 分子对接：`tool`，绑定 `molecular-docking`，产出 `docking_pose`、`affinity_report`。
5. 性质预测：`tool`，绑定 `molp-pc-property-prediction`，产出 `property_report`。
6. 先导优化：`tool`，绑定 `lead-optimizer`，产出 `optimized_lead`。
7. 结果汇总：`result`，汇总所有关键产物。

节点布局可以先横向为主，分支节点上下排列，模拟参考图片的流程结构。

## 组件拆分

新增组件建议：

| 组件 | 职责 |
| --- | --- |
| `WorkflowTemplateSelector.vue` | 模板选择和模板说明 |
| `WorkflowCanvas.vue` | 节点图容器、缩放、节点点击 |
| `WorkflowCanvasNode.vue` | 单个节点展示 |
| `WorkflowCanvasEdge.vue` | 连线展示 |
| `WorkflowNodeInspector.vue` | 右侧节点参数和运行面板 |
| `WorkflowNodeStatusBadge.vue` | 节点状态展示 |

第一版可用 CSS/SVG 自绘固定节点图，避免立刻引入重型画布库。若希望直接为二期拖拽铺路，可第一版即引入 Vue Flow。

## 画布库选型

推荐路径：

- 第一版：优先用 Vue Flow，关闭拖拽和连线编辑，仅使用节点、边、缩放、MiniMap、Controls。
- 二期：打开节点拖拽、连线编辑、删除节点、保存布局。

选型依据：

- Vue Flow 是 Vue 3 的可定制流程图组件，支持缩放、平移、选择、可拖拽元素、自定义节点和边，适合当前 Vue 技术栈。参考：https://vueflow.dev/
- AntV X6 是图编辑引擎，适合 DAG、流程图、血缘图等复杂图编辑场景，扩展能力强，但第一版接入成本更高。参考：https://x6.antv.antgroup.com/

结论：第一版建议使用 Vue Flow；如果后续要做企业级复杂图编辑、节点端口规则、框选、对齐线、小地图和插件体系，再评估 X6。

## 后端演进方案

第一版不强制新增后端表，模板可以前端内置。

二期需要保存流程草稿和运行历史时，新增：

- `workflow_templates`：系统模板定义。
- `workflow_runs`：用户一次流程运行。
- `workflow_run_nodes`：节点状态、参数、任务 ID、错误信息。
- `workflow_run_edges`：节点依赖和产物类型。

后端接口建议：

- `GET /api/v1/workflows/templates`
- `POST /api/v1/workflows/runs`
- `GET /api/v1/workflows/runs/{run_id}`
- `PATCH /api/v1/workflows/runs/{run_id}/nodes/{node_id}`
- `POST /api/v1/workflows/runs/{run_id}/nodes/{node_id}/execute`

第一版暂不实现这些接口，避免过早设计。

## 升级到自由拖拽画布

因为第一版已经使用 `nodes`、`edges`、`position`，二期升级路径清晰：

1. 解锁节点拖拽，保存 `position`。
2. 增加左侧工具库，工具拖入后创建 `tool` 节点。
3. 增加连线编辑，连线时校验 `producedOutputTypes` 与 `requiredInputTypes`。
4. 增加节点删除、复制、禁用。
5. 增加模板保存和复用。
6. 后端持久化自定义模板与运行实例。
7. 增加 DAG 校验，禁止循环依赖。
8. 增加“一键运行可执行节点”调度。

## 错误处理

- 工具缺失：节点显示 `needs_tool_selection`，右侧提示管理员配置工具。
- 输入缺失：节点显示 `idle`，右侧列出缺失的语义产物。
- 上游失败：下游节点禁用运行按钮，提示先修复上游。
- 任务失败：节点显示 `failed`，右侧展示错误信息和日志入口。
- 产物不兼容：产物绑定列表只展示兼容文件，并保留手动查看全部入口。

## 测试策略

前端测试：

- 模板节点和边生成测试。
- 节点状态计算测试。
- 上游更新导致下游 `invalidated` 的测试。
- 工具选择和参数草稿持久化测试。
- 产物语义类型匹配测试。
- 页面结构测试：画布、左侧步骤、右侧 Inspector 必须存在。

后端测试：

- 第一版仅复用现有任务和文件接口测试。
- 若新增 workflow 后端接口，再补充模板、运行、节点状态和权限测试。

手工验证：

- 未登录访问的跳转行为。
- AIDD 模板节点显示和状态变化。
- 单节点运行成功后产物进入下游候选。
- 任务失败时错误提示和日志入口可用。
- 桌面宽屏和普通笔记本宽度下不遮挡。

## 风险与控制

| 风险 | 控制方式 |
| --- | --- |
| 一次性做成自由编排导致周期过长 | 第一版固定模板，只做节点展示和逐节点运行 |
| 节点状态和现有任务状态映射混乱 | 统一通过 `WorkflowStepRecord` 计算 |
| 产物自动绑定错误 | 只按语义类型推荐，运行前仍展示给用户确认 |
| 画布库引入影响包体积 | 第一版评估 Vue Flow，必要时懒加载 `/workflow` 页面 |
| 后续难以升级自由拖拽 | 第一版即采用 `nodes`、`edges`、`position` 数据结构 |

## 建议里程碑

### M1：模板节点图静态展示

- 新增 AIDD 模板定义。
- 新增节点画布组件。
- 展示节点、连线、状态、选中态。

### M2：节点 Inspector 与现有运行能力对接

- 点击节点展示工具选择、参数表单、输入产物绑定。
- 复用任务创建接口运行当前节点。
- 记录 `taskByNode`。

### M3：产物流转和状态联动

- 节点完成后刷新产物。
- 下游自动推荐上游产物。
- 上游重跑后下游标记 `invalidated`。

### M4：体验完善

- 增加缩放、适配屏幕、MiniMap 或流程概览。
- 完善空状态、错误状态、加载状态。
- 补齐测试和团队使用说明。

## 结论

第一版应采用“模板式节点编排 + 逐节点运行 + 产物自动推荐”的方案。它能快速提升流程可视化体验，并最大限度复用当前工具、任务和产物系统。数据结构从第一版开始采用节点图模型，为后续自由拖拽编排画布保留升级空间。
