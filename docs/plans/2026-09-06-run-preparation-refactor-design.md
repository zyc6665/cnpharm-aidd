# Run Preparation 重构设计

## 1. 背景

平台已经形成 Tool Contract、标准 Artifact、Task、Workflow、Agent 计划等能力，但“准备一次工具运行”的逻辑仍分散在多个入口：

- `backend/app/tasks/service.py` 校验 `input_bindings`，并把标准 Artifact 投影为 legacy `file_ids` / `params`。
- `backend/app/services/workflow_scheduler.py` 解析工作流输入、上游节点输出、绑定决策、builtin 输入和 legacy SSH 文件字段。
- `backend/app/services/artifact_binding_resolver.py` 只处理单个 ArtifactVersion 的 role/readiness 策略，但被多个调用方直接使用。
- `frontend/src/composables/useStandaloneNodeRun.ts` 和 `frontend/src/components/workflow/WorkflowNodeRunPanel.vue` 也在构造 `input_bindings`、`builtin_inputs` 和文件入参。
- `frontend/src/workflow/preflight.ts` 根据任务和节点状态镜像一部分后端 readiness 状态。

这导致同一工具在工具详情页、节点独立运行、工作流运行、Agent 调度中可能出现不一致。重构的第一刀应把“运行准备”收成一个深模块，而不是直接重写工作流或执行器。

## 2. 目标

建立后端 `RunPreparation` 模块，作为所有运行入口的权威准备层：

- 统一工具详情页、节点独立运行、工作流节点运行、Agent 计划运行的输入准备口径。
- 统一处理普通参数、上传文件、已有 ArtifactVersion、工作流输入、上游节点输出。
- 统一输出 `PreparedRun`、`ReadinessReport`、`BindingDecision`。
- 保持现有 `TaskCreate`、`Task.extra_data.input_bindings`、`Task.extra_data.binding_decisions`、`TaskInput.file_ids`、legacy `params.input_files` 兼容。
- 让 `workflow_scheduler.py` 从“工具输入适配器”退回到“工作流节点调度器”。

## 3. 非目标

本阶段不做以下事情：

- 不重写整个工作流引擎。
- 不改数据库主模型和迁移。
- 不实现新的 Docking、MD、科学结果 Profile 或 DMTA 数据对象。
- 不移除 legacy SSH/builtin 输入兼容。
- 不要求前端立即调用新的后端 preview endpoint；第一阶段先保持现有前端 payload 兼容。
- 不执行 git commit，除非主人后续明确要求。

## 4. 设计原则

- **KISS**：先抽出当前已经存在的运行准备行为，避免一次性引入新执行模型。
- **YAGNI**：只覆盖当前 V1 主链路需要的 Artifact 输入、上传、绑定决策和 legacy 投影。
- **DRY**：消除 `tasks.service`、`workflow_scheduler`、前端 standalone run 中重复的 slot/file 投影规则。
- **SOLID**：`RunPreparation` 只负责准备运行；Task 创建只负责持久化和调度；Workflow 只负责节点依赖和状态推进。

## 5. 方案对比

### 方案 A：保守抽取 `RunPreparation`，推荐

新增 `backend/app/services/run_preparation.py`，先复用现有 `artifact_binding_resolver.py`，把标准绑定校验、role 决策、file 投影、builtin 输入投影集中到一个模块。`tasks.service` 和 `workflow_scheduler` 逐步改为调用它。

优点：风险低，测试容易补齐，保留现有 API 和数据形态。缺点：短期仍需要兼容部分旧字段。

### 方案 B：重写 Task/Workflow 创建流

一次性定义新 DTO、新内部命令和新工作流调度流，把所有入口改为 `RunPreparationInput -> PreparedRun -> TaskCommand`。

优点：最终形态最干净。缺点：影响范围大，容易破坏工具详情页、工作流、Agent 和 worker 执行链路，不适合作为第一刀。

### 方案 C：先统一前端 preview

先把前端 `useStandaloneNodeRun.ts`、`preflight.ts`、`contract-bindings.ts` 收敛成纯前端运行准备预览，再晚些改后端。

优点：界面反馈能较快改善。缺点：后端仍不是唯一权威，运行失败和预检成功不一致的问题继续存在。

结论：采用方案 A。

## 6. 推荐架构

```text
Run Surface
  ├─ Tool Detail Run
  ├─ Standalone Workflow Node Run
  ├─ Workflow Scheduler Node Run
  └─ Agent Planned Run
        │
        ▼
RunPreparationInput
        │
        ▼
RunPreparation Module
  ├─ Context Resolver
  ├─ Source Resolver
  ├─ Artifact Binding Resolver
  ├─ Legacy Projection
  └─ Readiness Reporter
        │
        ▼
PreparedRun / ReadinessReport
        │
        ▼
Task Creation + Executor
```

## 7. 模块接口

### 7.1 RunSurface

运行来源只表达“谁在发起运行”，不表达业务分支逻辑。

```python
RunSurface = Literal[
    "tool_detail",
    "standalone_node",
    "workflow_node",
    "agent_plan",
]
```

### 7.2 RunContext

```python
@dataclass(frozen=True)
class RunContext:
    surface: RunSurface
    user_id: str
    project_id: str | None = None
    workflow_run_id: str | None = None
    workflow_definition_id: str | None = None
    workflow_node_id: str | None = None
```

### 7.3 RunPreparationInput

```python
@dataclass(frozen=True)
class RunPreparationInput:
    tool: Tool
    tool_version: ToolVersion
    context: RunContext
    params: dict[str, Any]
    file_ids: list[str]
    input_bindings: dict[str, str]
    standard_input_uploads: dict[str, str]
    workflow_node: dict[str, Any] | None = None
    workflow_input_files: dict[str, str] | None = None
    workflow_node_states: dict[str, Any] | None = None
```

### 7.4 PreparedRun

```python
@dataclass(frozen=True)
class PreparedRun:
    ready: bool
    project_id: str | None
    params: dict[str, Any]
    file_ids: list[str]
    input_bindings: dict[str, str]
    standard_input_uploads: dict[str, str]
    binding_decisions: dict[str, dict[str, Any]]
    blocked_reason: str | None = None
```

### 7.5 ReadinessReport

第一阶段可以与 `PreparedRun` 合并返回；后续再拆 preview endpoint。

```python
@dataclass(frozen=True)
class ReadinessReport:
    ready: bool
    binding_decisions: dict[str, dict[str, Any]]
    missing_inputs: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    blocked_reason: str | None = None
```

## 8. 行为规则

### 8.1 输入来源优先级

对每个 Artifact input slot：

1. 工作流上游节点 ArtifactVersion。
2. 工作流外部输入文件。
3. 用户显式选择的 ArtifactVersion。
4. 用户直接上传的标准输入文件。
5. legacy `file_ids` / 文件字段。
6. 缺失输入。

### 8.2 ArtifactVersion 绑定

- 必须校验 ArtifactVersion 存在且可用。
- 有项目上下文时，ArtifactVersion 必须属于当前项目。
- 使用 `artifact_binding_resolver.resolve_artifact_binding()` 处理 type、role、readiness。
- `status != ready` 时不得创建任务，必须返回 `binding_decisions`。

### 8.3 标准上传

当前 schema 已有 `standard_input_uploads`，但服务层基本未实现。第一阶段只冻结接口与测试，第二阶段实现：

- 上传文件可以作为 slot 输入。
- 输出标准 Artifact 的任务需要归属项目；无项目时使用默认工作空间项目。
- 上传文件不冒充 ArtifactVersion，只作为 staged standard input。

### 8.4 Legacy 投影

为了兼容当前 SSH/builtin 工具：

- 对 builtin executor，投影为 `params.builtin_inputs[standard_type] = file_id`。
- 对 legacy SSH executor，投影为 `params.input_files[file_field] = input/<filename>`。
- 对 Tool Package v2/Remote 标准工具，保留 `input_bindings` 给标准 request builder。
- 投影逻辑只允许存在于 `RunPreparation` 或执行器内部兼容层，不再散落在工作流调度和前端组件中。

### 8.5 阻塞与状态

第一阶段继续兼容现有状态：

- `ready`
- `needs_preparation`
- `needs_conversion`
- `invalid`

后续再扩展：

- `missing`
- `ambiguous`
- `waiting_upstream`
- `project_required`

## 9. 调用方迁移

### 9.1 `backend/app/tasks/service.py`

保留 `create_and_schedule_tool_task()` 对外 Interface。内部把以下逻辑迁入 `prepare_run()`：

- `_validate_standard_input_bindings()`
- `_project_standard_input_bindings()`
- `_project_selected_file_to_legacy_params()`
- `_legacy_file_field_for_slot()`
- `_dedupe_ordered()`

`create_and_schedule_tool_task()` 只负责：加载工具和版本、补 project、调用 `prepare_run()`、写 Task/TaskInput、记录工具使用、触发 runner。

### 9.2 `backend/app/services/workflow_scheduler.py`

保留 `schedule_workflow_node()` 对外 Interface。内部改为：

1. 判断上游节点是否成功。
2. 构造 workflow run context 和 node params。
3. 调用 `prepare_workflow_node_run()` 或 `prepare_run()`。
4. 如果 blocked，把 `binding_decisions` 和 `blocked_reason` 写回 node state。
5. 如果 ready，创建 Task。

### 9.3 前端运行入口

第一阶段保持现状，只新增测试约束：

- 前端可以继续发送 `input_bindings`，但最终投影由后端决定。
- 前端可以展示自动绑定卡片，但不能成为权威 readiness 判断。
- 后续 preview endpoint 出现后，`preflight.ts` 只消费 `ReadinessReport`。

## 10. 测试策略

优先补后端测试，再迁移实现：

- `test/test_run_preparation.py`：覆盖输入绑定、legacy 投影、builtin 投影、blocking decision。
- `test/test_tasks_service_standard_inputs.py`：扩展到服务层，确保 create task 仍保存兼容字段。
- `test/test_workflow_scheduler.py`：迁移后保持现有工作流调度回归全部通过。
- `test/test_artifact_binding_resolver.py`：只保留纯 policy 测试，不承担 run context。
- 前端 `WorkflowNodeRunPanel.spec.ts`、`preflight.spec.ts`、`contract-bindings.spec.ts` 作为兼容回归。

## 11. 风险与控制

| 风险 | 控制 |
| --- | --- |
| 工作流主链路断裂 | 先写 `RunPreparation` tests，再迁移 `workflow_scheduler` 调用 |
| legacy SSH 参数丢失 | 固化 `params.input_files` 投影测试 |
| builtin 输入丢失 | 固化 `params.builtin_inputs` 投影测试 |
| ArtifactVersion 权限/项目归属绕过 | 在 `prepare_run()` 中集中校验 |
| 前端预检和后端执行不一致 | 短期以后端错误 detail 为准，后续引入 preview endpoint |
| 计划过度扩大 | 本轮只处理 Run Preparation，不碰 Executor Gateway 和 Result Manifest |

## 12. 验收标准

- 新增 `backend/app/services/run_preparation.py` 后，调用方不再复制标准 Artifact role/file 投影逻辑。
- `create_and_schedule_tool_task()` 仍能创建普通参数任务、legacy 文件任务、标准 ArtifactVersion 输入任务。
- `schedule_workflow_node()` 仍能处理 workflow input、上游 standard artifact、builtin 输入、legacy SSH 输入。
- raw protein 遇到 `require_prepared` 时继续被 blocked，并带 `binding_decisions`。
- prepared protein 遇到 legacy SSH 工具时继续只传 selected role 对应文件。
- 现有相关后端和前端回归测试通过。

## 13. 当前结论

可以开始重构，但第一阶段应只做 `RunPreparation` 权威化。直接重写工作流、执行器或前端工作台风险过大，不符合当前平台已有文档的模块地基顺序。

