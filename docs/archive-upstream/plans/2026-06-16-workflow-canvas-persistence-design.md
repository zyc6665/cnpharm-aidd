# 工作流画布持久化与运行设计

## 目标

在 `6.16` 已有模板式节点画布基础上，继续实现下一阶段能力：

1. 节点位置可编辑。
2. 流程定义可保存到后端。
3. 用户可加载、更新、删除自己的流程。
4. 提供基础一键运行入口。

## 第一批范围

本阶段做“可保存的自由布局画布”，不做完整流程调度引擎。

包含：

- 前端节点拖拽并更新 `position`。
- 后端保存流程定义 JSON。
- 前端保存/加载流程定义。
- 一键运行只提交当前已满足条件的工具节点，失败时停止并提示。

暂不包含：

- 后端工作流运行实例表。
- 自动等待上游任务完成后继续下游。
- 并发调度、条件分支、循环检测 UI。
- 多人协同编辑。

## 后端设计

新增模型 `WorkflowDefinition`：

- `id`
- `user_id`
- `name`
- `description`
- `template_id`
- `nodes`
- `edges`
- `selected_tool_by_node`
- `artifact_bindings_by_node`
- `status`
- `created_at`
- `updated_at`

新增 API：

- `GET /api/v1/workflows`
- `POST /api/v1/workflows`
- `GET /api/v1/workflows/{workflow_id}`
- `PUT /api/v1/workflows/{workflow_id}`
- `DELETE /api/v1/workflows/{workflow_id}`

权限：

- 必须登录。
- 普通用户只能访问自己的流程。
- 管理员也按“自己的流程”处理，避免误删团队流程。

## 前端设计

新增模块：

- `frontend/src/api/workflows.ts`
- `frontend/src/stores/workflow-definitions.ts`

扩展现有模块：

- `template-types.ts` 增加可保存快照类型。
- `workflow.ts` 增加节点位置覆盖、保存状态和当前流程 ID。
- `WorkflowTemplateCanvas.vue` 支持拖动节点，拖动结束发出 `move-node`。
- `workflow/index.vue` 增加保存、加载、另存为和运行按钮。

保存数据结构：

```ts
interface WorkflowDefinitionPayload {
  name: string
  description?: string
  template_id: string
  nodes: WorkflowCanvasNode[]
  edges: WorkflowCanvasEdge[]
  selected_tool_by_node: Record<string, string>
  artifact_bindings_by_node: Record<string, Record<string, string>>
  status: 'draft' | 'active' | 'archived'
}
```

## 一键运行策略

第一版一键运行不做异步 DAG 调度，只执行“当前已经 ready 的工具节点”：

1. 按模板节点顺序扫描。
2. 找到 `status === ready` 的工具节点。
3. 依次调用现有任务创建接口。
4. 记录 `taskByNode`。
5. 如果提交失败，停止流程。

后续若要自动等待上游完成，应新增后端 `workflow_runs` 和节点运行实例表。

## 测试策略

后端：

- schema 序列化测试。
- API surface 测试。
- 用户只能访问自己的流程。

前端：

- API 封装 surface 测试。
- store 保存/加载字段测试。
- 节点拖拽事件 surface 测试。
- 页面保存/加载/一键运行入口 surface 测试。
- `npm run build` 验证。

## 风险

- 直接保存 JSON 缺少强校验：用 Pydantic 基础结构先兜底，后续再做节点/边详细校验。
- 一键运行不是完整自动调度：UI 文案必须说明是“运行当前可运行节点”。
- 节点拖拽可能影响移动端：桌面开启拖拽，移动端保留点击选择优先。
