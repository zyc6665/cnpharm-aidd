# Project Agent Workflow Unification Design

## 背景

平台正在从旧 AIDD Agent 入口迁移到项目优先、会话驱动、Artifact 贯穿的研究工作台。当前 `/projects/:projectId/research` 已经具备项目会话、计划审批、事件流和 Artifact 展示的骨架；`/workflow` 页面仍保留旧 `AiddAgentPanel`，可以直接创建 `/agents/aidd/runs` 旧执行记录。

这会造成两个正式 Agent 入口、两套运行历史、两套产物归属和两套执行语义。后续标准 Artifact、工具契约和模型侧 adapter 统一后，平台侧不能再让用户从旧入口绕过项目上下文。

## 已确认决策

1. `/projects/:projectId/research` 是唯一正式 Agent 入口。
2. `/workflow` 不再创建旧 Agent 执行记录，只保留手动工作流编排和 AI 工作流草稿生成。
3. `/workflow` 的 Agent 模式降级为“工作流草稿助手”。
4. 草稿助手必须绑定 `project_id`；没有项目上下文时只能引导选择或创建项目。
5. 草稿生成后自动保存成当前项目下的 `WorkflowDefinition(status=draft)`，并导入 workflow canvas 供用户编辑。
6. 第一阶段项目 Agent 只打通 `protein_structure@1 -> LVpocket -> binding_pocket@1` 最小闭环。
7. 项目 Agent 审批后的执行接统一任务系统标准 Task，不复活旧 AIDD service。

## 页面职责

### 项目研究页

项目研究页承担正式 Agent 能力：

- 项目记忆和会话历史
- Artifact 选择和引用
- 计划生成、审批、拒绝、分支
- 标准 Task 创建和远端进度回流
- ArtifactVersion 入库、lineage、渲染和可视化

### Workflow 页面

Workflow 页面承担工作台能力：

- 手动工作流画布编辑
- 节点工具选择、输入绑定、预检和手动运行
- 历史 WorkflowRun 查看
- 项目化 AI 草稿生成

Workflow 页面不再承担正式 Agent 运行历史、同步、取消和旧 AIDD 运行创建。

## 后端边界

`/agents/aidd/*` 保持 deprecated 和 feature flag，仅用于兼容或历史数据清理。新产品路径不再从前端主界面调用旧 run 创建、同步、取消和历史列表。

`/workflows` 需要显式支持项目归属：

- `WorkflowDefinitionCreate.project_id`
- `WorkflowDefinitionUpdate.project_id`
- `WorkflowDefinitionResponse.project_id`
- `GET /workflows?project_id=...` 过滤当前用户在项目下的定义
- 创建或更新带 `project_id` 的定义时校验项目成员权限

## 前端边界

`AiddAgentPanel` 应改造或替换为项目化草稿助手：

- 不调用 `createAiddAgentRun`
- 不展示旧 Agent 历史、同步、取消、运行 timeline
- 必须选择项目后才能生成草稿
- 生成草稿后保存 `WorkflowDefinition(draft, project_id)`
- 保存成功后把草稿导入当前 workflow canvas

`/workflow` manual 模式仍可全局使用；AI 草稿助手必须项目化。

## 验收标准

第一批完成时应满足：

- 用户不能从 `/workflow` 创建旧 `/agents/aidd/runs`
- `/workflow` 的 Agent tab 文案和行为清楚表达“草稿助手”
- `WorkflowDefinition` API 能创建、返回和按 `project_id` 过滤项目草稿
- 前端保存 workflow definition 时可传 `project_id`
- 相关 backend/frontend 测试覆盖上述行为

