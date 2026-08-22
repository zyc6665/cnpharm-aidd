# Workflow Binding Resolver 设计

## 1. 背景

当前工具详情页、节点独立运行、工作流全流程运行都在处理输入来源、文件、ArtifactVersion、项目上下文和 legacy 参数投影。逻辑分散后会导致同一工具在不同入口表现不一致。

Binding Resolver 的目标是把“如何满足工具输入”收敛为一个深模块。

## 2. 模块定位

Binding Resolver 不是 UI 组件，也不是执行器。它是运行准备模块。

```text
Tool Contract + Run Context + Input Sources
        │
        ▼
Binding Resolver
        │
        ▼
TaskCreate payload / Workflow node readiness / Binding decisions
```

## 3. 输入模型

```ts
interface ResolveBindingInput {
  toolContract: ToolContract
  runContext: RunContext
  parameterValues: Record<string, unknown>
  selectedArtifactVersions: Record<string, string>
  uploadedFiles: Record<string, string>
  workflowSources?: Record<string, WorkflowSourceRef>
  upstreamArtifacts?: Record<string, UpstreamArtifactRef>
}
```

解释：

- `toolContract`：工具标准契约。
- `runContext`：项目、默认工作空间或 file-only。
- `parameterValues`：普通参数。
- `selectedArtifactVersions`：用户选择的已有 ArtifactVersion。
- `uploadedFiles`：用户直接上传文件。
- `workflowSources`：工作流中 slot 来源。
- `upstreamArtifacts`：已完成上游节点输出。

## 4. 输出模型

```ts
interface ResolveBindingResult {
  ready: boolean
  params: Record<string, unknown>
  fileIds: string[]
  inputBindings: Record<string, string>
  standardInputUploads: Record<string, string>
  bindingDecisions: Record<string, BindingDecision>
  missingInputs: MissingInput[]
  preparationSuggestions: PreparationSuggestion[]
  warnings: BindingWarning[]
}
```

## 5. BindingDecision

```ts
interface BindingDecision {
  slotName: string
  type: string
  source: 'artifact_version' | 'uploaded_file' | 'workflow_input' | 'upstream_node'
  status: 'ready' | 'missing' | 'needs_preparation' | 'invalid_type' | 'invalid_role'
  selectedFileId?: string
  selectedArtifactVersionId?: string
  selectedRole?: string
  reason?: string
  suggestedPreparationTool?: string
}
```

## 6. 解析优先级

对每个 `artifacts.inputs[]` slot：

1. 工作流上游节点输出。
2. 工作流外部输入绑定。
3. 用户选择的项目 ArtifactVersion。
4. 用户直接上传文件。
5. 参数 schema legacy 文件字段。
6. 缺失输入。

说明：

- 工作流中，上游输出优先级最高。
- 工具独立运行中，用户显式选择优先于上传。
- 有 ArtifactVersion 时使用 `input_bindings`。
- 直接上传时使用 `standard_input_uploads`。

## 7. Run Context 规则

| 场景 | 允许输入 | 输出归属 |
| --- | --- | --- |
| 无 project 独立运行 | 参数、上传文件 | 标准输出进入默认工作空间 |
| 有 project 独立运行 | 参数、上传文件、项目 ArtifactVersion | 当前项目 |
| 工作流有 project | 上游、工作流输入、项目 ArtifactVersion | 当前项目 |
| 工作流无 project | 上游、上传/默认工作空间输入 | 默认工作空间 |

规则：

- 选择已有 ArtifactVersion 必须有 project。
- 标准输出必须有归属 project 或默认工作空间。
- file-only 工具可以无 project。

## 8. Role 解析规则

ArtifactVersion 绑定时：

1. 校验 Artifact type 等于 slot type。
2. 校验 `required_roles` 全部存在。
3. 按 `role_preferences` 选择最优文件。
4. 若无 preference，选择 primary role。
5. 若 role 不满足，返回 `needs_preparation` 或 `invalid_role`。

直接上传时：

1. 根据 slot type 查标准类型 primary role。
2. 将上传文件作为 staged standard input。
3. 文件扩展名不满足时返回 warning 或 error。
4. 不声明为已持久化 ArtifactVersion。

## 9. Legacy 参数投影

部分旧工具仍然需要 `input_files` 或某个 file 字段。

Resolver 应将标准绑定投影为 legacy 输入：

```text
ArtifactVersion / uploaded file
        │
        ▼
selected file id
        │
        ├─ Task.file_ids
        ├─ params.input_files[field] for ssh_job
        └─ params.builtin_inputs[type] for builtin
```

这个投影应位于 Resolver 或后端任务准备模块，不应散落在 UI 和 workflow scheduler。

## 10. 前后端职责

### 10.1 前端 Resolver

用途：

- 表单必填状态。
- 预检展示。
- 构造 TaskCreate payload。
- 给用户解释缺失项。

前端 Resolver 可以预测，但不是最终权威。

### 10.2 后端 Resolver

用途：

- 权限校验。
- ArtifactVersion 项目校验。
- 文件存在性校验。
- role 和 readiness 校验。
- legacy 参数投影。
- 输出 project 归属确定。

后端 Resolver 是最终权威。

## 11. 工作流集成

工作流节点调度时：

```text
WorkflowRun node ready?
  │
  ├─ 上游节点是否成功
  ├─ 上游标准 ArtifactVersion 是否存在
  ├─ 必填 workflow input 是否已提供
  └─ Binding Resolver 是否 ready
```

节点 ready 后创建 Task：

```text
TaskCreate
 ├─ project_id
 ├─ params
 ├─ file_ids
 ├─ input_bindings
 └─ standard_input_uploads
```

## 12. 预检消息设计

预检应使用研发人员能理解的语言：

| 类型 | 示例 |
| --- | --- |
| missing_input | “缺少 protein 输入，请连接上游蛋白节点或上传蛋白结构。” |
| waiting_upstream | “等待 Fetch PDB 产出 protein_structure@1。” |
| needs_preparation | “当前蛋白缺少 prepared_pdb，建议插入 Protein Preparation。” |
| invalid_role | “选择的蛋白 Artifact 缺少 receptor_pdbqt，不能用于 Vina 对接。” |
| invalid_type | “LVpocket 需要 protein_structure@1，但上游输出是 ligand_structure@1。” |
| project_required | “选择已有 Artifact 需要项目上下文；请进入项目或改为上传文件。” |

## 13. 失败处理

- Resolver 返回 missing 时，前端禁止运行并给出补救动作。
- Resolver 返回 needs_preparation 时，可允许用户强行运行或建议插入处理节点，取决于 readiness_policy。
- 后端校验失败时，应把 binding_decisions 写入错误 detail。
- 工作流节点失败时，应保存到 node state，加载后继续展示。

## 14. 测试矩阵

| 场景 | 期望 |
| --- | --- |
| 无 project + 上传蛋白 + LVpocket | 可创建任务，输出进入默认工作空间 |
| 有 project + 选择蛋白 Artifact | 发送 input_bindings 和 project_id |
| 有 project + 上传蛋白 | 发送 standard_input_uploads 和 project_id |
| Fetch PDB -> LVpocket | 自动传递 protein ArtifactVersion |
| 原始蛋白 -> Vina | 提示需要 receptor_pdbqt |
| 保存工作流再加载 | 节点槽位和任务绑定恢复 |

## 15. 迁移步骤

1. 前端新增标准 Run Context 和 Binding Resolver domain 模块。
2. 后端新增标准 task input preparation 模块。
3. 工具详情页改用 Resolver。
4. 节点独立运行改用 Resolver。
5. 工作流调度改用 Resolver。
6. 删除重复的 slot/file/input 投影逻辑。

## 16. 禁止事项

- 禁止在组件中硬编码某个工具的 Artifact 映射。
- 禁止 workflow scheduler 直接猜参数字段。
- 禁止前端通过字符串拼接生成文件运行路径。
- 禁止后端执行器绕过 Resolver 直接读取项目 Artifact。
