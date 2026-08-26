# Tool Contract v2 规范

## 1. 目标

Tool Contract v2 是平台对工具能力的统一理解方式。它要让工具可以同时被工具详情页、工作流、智能体、任务执行器和管理后台使用，而不需要为每个入口单独适配。

## 2. 设计原则

1. 工具契约描述能力，不描述某次运行。
2. Project 属于 Run Context，不属于 Tool Contract。
3. 标准数据输入输出使用 `artifacts.inputs` 和 `artifacts.outputs`。
4. 普通参数使用 `parameters_schema`。
5. 执行方式通过 executor 和 runtime 声明。
6. 资源需求通过 resource profile 声明。
7. 新工具不应使用 legacy `agent_capability` 作为主契约。

## 3. 规范结构

```yaml
api_version: aidd.sciminer/tool-contract.v2
kind: ToolContract
metadata:
  slug: lvpocket-pocket-prediction
  name: LVpocket Pocket Prediction
  version: 1.0.0
  description: Predict binding pockets from protein structures.
exposure:
  direct_run: true
  workflow: true
  agent: true
parameters_schema:
  type: object
  properties:
    model_choice:
      type: string
      enum: [default]
    device:
      type: string
      enum: [cpu, cuda]
artifacts:
  inputs:
    - name: protein
      type: protein_structure@1
      required: true
      role_preferences: [prepared_pdb, structure_file]
      readiness_policy: prefer_prepared_warn_raw
      suggested_preparation_tool: builtin-protein-preparation
  outputs:
    - name: pocket
      type: binding_pocket@1
      cardinality: one
      required: true
resource_profile:
  tier: cpu-medium
  cpu: 4
  memory_gb: 8
  gpu_required: false
  expected_minutes: 5
  timeout_minutes: 30
executor:
  type: ssh_job
runtime:
  mode: managed
examples:
  - name: smoke
    smoke: true
    parameters:
      model_choice: default
    input_artifacts:
      protein:
        type: protein_structure@1
        files:
          structure_file:
            filename: example.pdb
            sha256: <sha256>
```

## 4. 字段说明

### 4.1 `metadata`

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `slug` | 是 | 全局唯一，kebab-case |
| `name` | 是 | 展示名称 |
| `version` | 是 | SemVer |
| `description` | 建议 | 面向用户的能力描述 |

### 4.2 `exposure`

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `direct_run` | true | 是否允许工具独立运行 |
| `workflow` | true | 是否进入工作流节点库 |
| `agent` | true | 是否可被智能体推荐 |

### 4.3 `parameters_schema`

JSON Schema object，只放普通参数：

- 数字阈值。
- 枚举选项。
- 文本输入。
- 布尔开关。
- 运行模式。

不应放：

- 标准 Artifact 文件输入。
- 项目 ID。
- 用户 ID。
- 工作流 ID。
- 远端服务器凭据。

### 4.4 `artifacts.inputs`

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 工具内部稳定 slot 名 |
| `type` | 是 | 标准 Artifact ref |
| `required` | 是 | 是否必填 |
| `role_preferences` | 否 | 优先选择的文件角色 |
| `required_roles` | 否 | 必须具备的文件角色 |
| `readiness_policy` | 否 | 原始/已处理输入策略 |
| `suggested_preparation_tool` | 否 | 建议插入的准备工具 slug |

### 4.5 `artifacts.outputs`

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 输出 slot 名 |
| `type` | 是 | 标准 Artifact ref |
| `cardinality` | 是 | `one` 或 `many` |
| `required` | 是 | 结果中是否必须产出 |
| `provided_roles` | 建议 | 工具会提供的文件角色 |

### 4.6 `resource_profile`

资源画像用于预检、调度和运维：

```yaml
resource_profile:
  tier: gpu-large
  cpu: 16
  memory_gb: 64
  gpu_required: true
  gpu_memory_gb: 24
  expected_minutes: 120
  timeout_minutes: 480
  parallelism: 1
```

### 4.7 `executor`

标准 executor 类型：

- `builtin`
- `python_script`
- `docker_image`
- `ssh_job`
- `remote_api`
- `k8s_job`
- `slurm_job`

说明：

- executor 只声明执行方式。实际 credentials、project_id、task_id 由平台运行时注入。
- 工具是否以 Tool Package 交付不属于 executor 类型，应由 `package_format` 或 Tool Package manifest 来源表达。
- `k8s_job` 和 `slurm_job` 是重计算生产化执行器，第一阶段可以先由 `ssh_job` 过渡，但契约层应保留标准类型。

### 4.8 `package_format`

可选字段，用于说明工具交付格式：

```yaml
package_format: tool_package_v2
```

说明：

- `package_format` 描述工具如何交付。
- `executor.type` 描述工具如何运行。
- 从 Tool Package v2 导入的工具也必须落到具体 executor，例如 `docker_image`、`ssh_job`、`k8s_job`、`slurm_job` 或 `remote_api`。

## 5. 与 Tool Package v2 的关系

Tool Package v2 是模型/工具交付格式，Tool Contract v2 是平台归一化后的运行契约。

```text
Tool Package Manifest
        │
        ▼
Tool Contract Builder
        │
        ▼
Tool Contract v2
        │
        ├─ 工具详情页
        ├─ 工作流节点库
        ├─ 智能体工具摘要
        └─ 任务执行准备
```

## 6. 与 Remote API 的关系

Remote API 自注册服务提供 remote-tool manifest。平台拉取 manifest 后也转换为 Tool Contract v2。

```text
Remote Service /manifest
        │
        ▼
Remote Tool Manifest
        │
        ▼
Tool Contract v2
```

## 7. 工作流兼容规则

工具能进入工作流必须满足：

1. `exposure.workflow = true`。
2. `artifacts.outputs` 至少有一个，或工具是纯报告/终止节点。
3. 所有 Artifact type 都存在于标准 registry。
4. `validation.status = valid`。
5. `capability.enabled = true` 或可由 artifacts 派生。

## 8. Agent 兼容规则

智能体使用工具时只读取归一化摘要：

- slug。
- name。
- description。
- stage/capability。
- artifacts.inputs。
- artifacts.outputs。
- resource_profile。
- examples。
- validation status。

智能体不得依赖工具私有 runtime 配置进行计划。

## 9. 校验规则

导入或发布工具时必须校验：

- slug 格式。
- version 格式。
- JSON Schema 合法。
- Artifact 输入输出类型存在。
- role_preferences 和 required_roles 属于标准类型。
- required output 在 result contract 中可生成。
- executor 类型受支持。
- resource_profile 数值合法。
- smoke example 可执行或明确未验证状态。

## 10. Legacy 兼容

现有工具可能只有：

- `input_schema`。
- `output_schema`。
- `agent_capability`。
- `artifacts`。
- executor config。

兼容策略：

1. 优先使用 `artifacts` 生成标准槽位。
2. 没有 `agent_capability` 时，可从 artifacts 派生 workflow capability。
3. legacy 文件字段通过 Run Preparation Module 投影。
4. 新工具禁止只写 legacy `agent_capability`。

## 11. 示例：蛋白处理工具

```yaml
metadata:
  slug: builtin-protein-preparation
  name: Protein Preparation
  version: 1.0.0
parameters_schema:
  type: object
  properties:
    ph:
      type: number
      default: 7.4
    remove_water:
      type: boolean
      default: true
artifacts:
  inputs:
    - name: protein
      type: protein_structure@1
      required: true
      role_preferences: [raw_structure_file, structure_file]
  outputs:
    - name: prepared_protein
      type: protein_structure@1
      cardinality: one
      required: true
      provided_roles: [prepared_pdb, receptor_pdbqt, preparation_report_json]
```

## 12. 禁止事项

- 禁止把 project_id 放入 Tool Contract。
- 禁止把工具部署密钥写入 contract。
- 禁止在工作流里为某个工具写专属字段映射。
- 禁止输出未注册标准类型。
- 禁止使用无版本 artifact type 作为新工具契约。
