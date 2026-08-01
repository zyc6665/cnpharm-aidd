# Unified Artifact Tool Contract Design

## 背景

当前平台已经有 `ToolContract`、AIDD Agent 动态工具注册、workflow 语义连线、
typed artifacts、Tool Package 等基础能力，但工具系统仍存在一个核心结构问题：
平台侧在为不同模型反复适配字段。

典型表现：

- 旧工具把 `input_schema`、`output_schema`、`agent_capability`、`output_globs` 放在
  `ToolVersion.config` 中，字段含义混杂。
- Agent / workflow 依赖 `semantic_inputs`、`semantic_outputs`、`output_rules` 再次解释
  工具输入输出。
- worker 任务输出主要保存 `TaskOutput.result` 和 `TaskOutput.file_ids`，产物类型、
  文件角色、标准校验结果没有成为任务输出的一等公民。
- 前端工具创建页仍要求管理员手动填写 Agent 输入语义映射、输出语义映射和 JSON
  Schema。
- `artifact_type`、`semantic_type`、文件格式名和模型专属产物名混用，导致模型越多，
  平台分支越多。

本设计的核心方向是：**平台契约固定，模型工具适配平台**。模型部署时允许修改原始
模型代码或增加 wrapper / adapter，把原始模型输入输出转换为平台标准输入输出。
平台不再为每个模型新增不同字段或模型专属映射。

## 目标原则

1. 平台只承认受控的标准 Artifact 类型，不允许新工具自由创造语义字符串。
2. 工具包 manifest 声明标准输入、标准输出、参数 schema、运行变体和 adapter 信息。
3. 模型 runner 只消费标准 `request.json` 和本地 staged 文件，不直接访问平台数据库或
   对象存储内部。
4. 模型 runner 只输出标准 `result.json` v2；平台据此创建标准 ArtifactVersion。
5. Agent / workflow 只按标准 Artifact 输入槽和输出槽编排，不再要求用户填写语义映射。
6. 文件输入不再放在参数 JSON Schema 中；参数 schema 只描述非文件参数。
7. GPU / CPU / DCU 等执行资源由 variant 和 deployment profile 管理，不作为普通模型参数。
8. 旧 `agent_capability`、旧 semantic alias、旧 `file_ids` 链路只保留兼容和迁移用途。

## 标准 Artifact 类型

标准类型是平台协议，源头放在仓库内版本化注册表中，数据库只缓存或展示，不作为源头。

建议目录：

```text
backend/app/artifact_standards/
  registry.py
  schemas/
    protein_structure.v1.yaml
    binding_pocket.v1.yaml
    molecule_table.v1.yaml
    ligand_structure.v1.yaml
    run_report.v1.yaml
    relations.yaml
```

MVP 只定义服务于 `LVpocket -> Pocket2Mol -> 结果展示/校验` 闭环的最小集合：

- `protein_structure@1`
- `binding_pocket@1`
- `molecule_table@1`
- `ligand_structure@1`
- `run_report@1`

可在后续真实工具需求出现后增加：

- `score_table@1`
- `docking_pose@1`

标准类型命名不携带文件格式后缀。文件格式由类型内的文件角色定义，例如
`binding_pocket@1` 可以包含 PDB 和 JSON，不应命名为 `pocket_pdb`。

### `protein_structure@1`

用于用户上传蛋白结构或上游工具生成的蛋白结构。

必需文件角色：

- `structure_file`
  - 允许格式：PDB
  - 推荐文件名：`structure.pdb`
- `metadata_json`
  - 允许格式：JSON
  - 必需字段：`chain_ids`、`residue_count`、`atom_count`、`structure_format`、
    `source_filename`

用户上传 PDB 后，应由平台 importer / validator 包装为 `protein_structure@1`
ArtifactVersion，再进入 Agent / workflow。

### `binding_pocket@1`

用于可进入下游分子生成、对接、可视化的标准口袋产物。无论 LVpocket 或其他模型原始
输出是什么，adapter 必须补齐该标准格式，才能声明产出 `binding_pocket@1`。

必需文件角色：

- `residue_pocket_pdb`
  - 残基级口袋 PDB
  - 给需要 residue context 的生成模型使用
- `atom_pocket_pdb`
  - 原子级或裁剪口袋 PDB
  - 给坐标生成、dock、可视化使用
- `pocket_metadata_json`
  - 必需字段：`center`、`bbox`、`residue_ids`、`atom_ids`、`source_protein_ref`

平台不维护运行时 quality / constraints 决策。适配质量在工具发布审核和 validator 中解决。
Agent / workflow 只做标准类型版本匹配。

### `molecule_table@1`

用于批量分子结果、SMILES 表、排序表的标准集合视图。

建议文件角色：

- `table_file`
  - 允许格式：CSV 或 JSON
  - 必需字段至少包含稳定分子 ID
- `metadata_json`
  - 描述表字段、排序依据、来源任务和关联 ligand artifact

### `ligand_structure@1`

用于单个小分子结构。批量生成时，一个工具输出可以返回多个 `ligand_structure@1`
ArtifactVersion。

建议文件角色：

- `structure_file`
  - 允许格式：SDF
- `metadata_json`
  - 包含 ligand ID、来源行 ID、基础分子属性等

### `run_report@1`

用于运行报告、日志摘要、非标准辅助产物索引。

建议文件角色：

- `report_json`
- 可选 `report_markdown`

非标准输出、原始模型输出、中间文件、日志、debug bundle 不进入自动编排链路，可以挂在
`run_report@1` 或 TaskOutput 辅助文件上。

## 受控 Relation 类型

Artifact relation 也必须平台受控，不能由工具自由写字符串。MVP 白名单：

- `derived_from`
- `contains`
- `describes`
- `ranked_by`
- `validated_by`
- `visualized_by`

常见用途：

- `molecule_table@1 contains ligand_structure@1[]`
- `run_report@1 describes binding_pocket@1`
- `binding_pocket@1 derived_from protein_structure@1`

平台入库时校验 relation 引用是否存在，关系类型是否在白名单中。

## Tool Package Manifest v2 草案

新工具主路径应从手填旧 `ToolVersion.config` 改为注册 Tool Package manifest。旧工具仍可运行，
但新工具不应再要求管理员填写 `agent_capability`。

示例草案：

```yaml
api_version: aidd.sciminer/tool-package.v2
kind: ToolPackage
metadata:
  slug: lvpocket-pocket-prediction
  name: LVpocket Pocket Prediction
  version: 1.0.0
  description: Predict binding pockets and adapt model output to platform standard artifacts.

artifacts:
  inputs:
    - name: protein
      type: protein_structure@1
      required: true
  outputs:
    - name: pocket
      type: binding_pocket@1
      cardinality: one
      required: true
    - name: report
      type: run_report@1
      cardinality: one
      required: false

parameters_schema: schemas/parameters.schema.json

adapter:
  input:
    - input: protein
      method: direct_file_mount
  output:
    - output: pocket
      method: lvpocket_voxel_to_residue_and_atom_pocket
      assumptions:
        - top_ranked_pocket_selected
      limitations:
        - original_model_does_not_emit_native_residue_confidence
      validator_profile: binding_pocket_v1_core

exposure:
  agent: true
  workflow: true
  direct_run: true

variants:
  - name: cpu
    accelerator: cpu
    executor_types: [container, cli]
    image: registry.local/lvpocket:1.0.0-cpu
    entrypoint: ["/app/runner/entrypoint.sh"]
    resources:
      cpu: 4
      memory_mb: 8192
  - name: cuda
    accelerator: nvidia_cuda
    executor_types: [container, remote_job]
    image: registry.local/lvpocket:1.0.0-cuda
    entrypoint: ["/app/runner/entrypoint.sh"]
    resources:
      cpu: 4
      memory_mb: 16384
      devices: ["nvidia.com/gpu"]
      driver: ">=535"
```

### 与旧 manifest 的差异

- `semantic_type` 和 `artifact_type` 合并为标准 `type`，如 `binding_pocket@1`。
- 文件输入不再写进 parameter schema。
- `agent_capability` 不再由管理员手填，而是从 `artifacts.inputs/outputs` 和 `exposure`
  自动派生。
- `host`、`username`、`password_ref`、`remote_base_dir`、`container_name` 等基础设施信息
  不进入 Tool Package。

## 标准 Request v1

runner 只看到标准 request 和本地 staged 文件。

```json
{
  "request_version": "aidd.sciminer/request.v1",
  "task": {
    "id": "task-id",
    "tool_slug": "lvpocket-pocket-prediction",
    "tool_version": "1.0.0"
  },
  "inputs": {
    "protein": {
      "artifact_version_id": "artifact-version-id",
      "type": "protein_structure@1",
      "files": {
        "structure_file": {
          "path": "input/protein/structure.pdb",
          "sha256": "..."
        },
        "metadata_json": {
          "path": "input/protein/metadata.json",
          "sha256": "..."
        }
      },
      "metadata": {}
    }
  },
  "parameters": {
    "threshold": 0.5
  },
  "execution": {
    "variant": "cuda",
    "accelerator": "nvidia_cuda",
    "work_dir": ".",
    "output_dir": "output"
  }
}
```

任务执行层按 `inputs.name -> ArtifactVersion` 绑定。调度层可按标准类型寻找候选产物，
但写入任务时必须落到工具输入槽名，避免同一工具多个同类型输入冲突。

## 标准 Result v2

输出以逻辑 Artifact 为单位，Artifact 内含固定文件角色集合。

```json
{
  "result_version": "aidd.sciminer/result.v2",
  "artifacts": {
    "pocket": {
      "name": "Top pocket",
      "type": "binding_pocket@1",
      "files": {
        "residue_pocket_pdb": {
          "path": "artifacts/pocket/residue.pdb",
          "sha256": "...",
          "content_type": "chemical/x-pdb"
        },
        "atom_pocket_pdb": {
          "path": "artifacts/pocket/atom.pdb",
          "sha256": "...",
          "content_type": "chemical/x-pdb"
        },
        "pocket_metadata_json": {
          "path": "artifacts/pocket/metadata.json",
          "sha256": "...",
          "content_type": "application/json"
        }
      },
      "summary": {},
      "metrics": {}
    }
  },
  "relations": [
    {
      "from": "pocket",
      "to": "protein",
      "type": "derived_from"
    }
  ],
  "summary": {},
  "metrics": {}
}
```

安全规则：

- `path` 必须是相对 `output_dir` 的路径。
- 不允许绝对路径。
- 不允许 `..` 路径逃逸。
- 平台必须重新计算 sha256，不能只信任 runner 声明。
- `content_type` 可由 runner 提供，但平台可以复核或覆盖。
- 缺少 required 文件角色时，任务标准输出入库失败。

`cardinality: many` 输出用列表表达：

```json
{
  "artifacts": {
    "generated_ligands": [
      {
        "name": "ligand_001",
        "type": "ligand_structure@1",
        "files": {
          "structure_file": {
            "path": "ligands/001.sdf",
            "sha256": "..."
          }
        }
      }
    ]
  }
}
```

## Artifact 存储模型

标准 Artifact 是逻辑产物，不等同于单文件。现有 `artifact_versions` 更接近单文件版本，
MVP 需要增加文件角色映射。

建议迁移：

```text
artifacts
- id
- project_id
- created_by
- standard_type
- standard_version
- name
- description
- latest_version_id
- source_task_id

artifact_versions
- id
- artifact_id
- created_by
- version
- validation_status
- validation_errors
- manifest_json
- summary_json
- metrics_json
- expires_at

artifact_version_files
- id
- artifact_version_id
- role
- file_id
- is_primary
- sort_order
```

执行层、Agent、workflow 主链路传 `ArtifactVersion.id`，不传 latest Artifact ID 或散乱
file_id。`TaskOutput.file_ids` 保留为兼容字段，但不再作为新标准链路的主数据。

## Importer、Validator、Converter

分层规则：

- 核心 validator 是平台强制能力，任何标准 ArtifactVersion 入库和进入自动编排前必须通过。
- importer / converter 可以作为可编排工具注册，但它们产出的 ArtifactVersion 仍必须过核心
  validator。
- 模型专属 adapter 随工具包交付，不进入平台核心代码。

示例：

- 上传 PDB -> importer -> `protein_structure@1`
- LVpocket 原始输出 -> 工具包 adapter -> `binding_pocket@1`
- Pocket2Mol 原始输出 -> 工具包 adapter -> `molecule_table@1` + `ligand_structure@1[]`

## Agent 与 Workflow

新标准工具的 Agent 注册从 manifest 自动派生：

```text
tool_slug
name
description
inputs: [{name, type, cardinality}]
outputs: [{name, type, cardinality}]
parameters: simplified schema
```

LLM 不需要看到 SSH 主机、容器名、文件角色路径、validator 实现或数据库表结构。

LLM 生成计划后，平台必须做确定性预检：

- 工具存在且已发布。
- exposure 允许 agent / workflow 使用。
- 输入槽全部绑定 ArtifactVersion。
- Artifact type/version 严格相等匹配。
- cardinality 匹配。
- 参数 schema 通过。
- 用户有 ArtifactVersion 访问权限。
- workflow 无环。
- 至少一个 variant/profile 可调度。

MVP 阶段不做自动跨版本转换，`type@version` 必须严格相等。converter 留到后续。

Workflow UI 应从“语义映射编辑器”改成“标准 Artifact 输入/输出槽连线”：

```text
Inputs
- protein: protein_structure@1

Outputs
- pocket: binding_pocket@1
- report: run_report@1
```

## Deployment Profile

Tool Package 不携带真实基础设施连接信息。基础设施绑定独立为 deployment profile，可复用于
多个工具包 variant。

示例 profile：

```text
local_docker_cpu
kaiwu_4090_docker_exec
h100_cluster_slurm
dcu_remote_job
```

profile 描述：

- executor backend
- host / queue / credential ref
- workspace root
- container mapping
- network policy
- artifact staging policy

Agent / workflow 默认不选择 profile。调度器根据 variant 资源需求、profile 可用性和策略选择。
用户可显式覆盖执行偏好，但不接触真实凭据和机器细节。

## Legacy 兼容与迁移

采用“双轨兼容、单主路径推进”：

- 新工具主路径：Tool Package manifest + standard Artifact + request/result 协议。
- 旧工具保留运行：继续读取 `ToolVersion.config`、`agent_capability`、`output_globs`。
- 旧 semantic alias 只在 legacy import / migration 边界使用。
- 新 Tool Package 校验必须拒绝 alias。
- 旧工具 UI 标记为 Legacy compatibility，并提供迁移入口。

旧 alias 迁移示例：

```text
protein_pdb / protein_structure -> protein_structure@1
pocket_pdb / pocket_result      -> binding_pocket@1
generated_ligand                -> ligand_structure@1 或 molecule_table@1
smiles_csv                      -> molecule_table@1
ranking_csv                     -> molecule_table@1 或 score_table@1
```

## MVP 闭环

首批只做代表性闭环，不一次性迁移全部模型：

1. LVpocket
   - 输入：`protein_structure@1`
   - 输出：`binding_pocket@1`
2. Pocket2Mol
   - 输入：`binding_pocket@1`
   - 输出：`molecule_table@1` + `ligand_structure@1[]` + `run_report@1`
3. Artifact 渲染 / 校验
   - 展示 protein、pocket、molecule table、ligand structure、run report

## 非目标

- 不在 MVP 做跨版本 converter 自动插入。
- 不一次性迁移 FlowPepDock、MMCD、TheraPainter 等复杂工具。
- 不让后台动态编辑标准类型和 relation 白名单。
- 不再为新工具增加模型专属平台字段。
- 不在 Agent 运行时维护 quality / constraints 决策系统；质量问题由 adapter、validator 和发布审核解决。

## 验证标准

MVP 完成时应满足：

- 新工具包只能引用标准 Artifact 类型。
- 标准 request / result schema 有纯单元测试覆盖。
- worker 能从 result.v2 创建多文件角色 ArtifactVersion。
- 用户上传 PDB 能包装为 `protein_structure@1`。
- LVpocket 工具包能产出标准 `binding_pocket@1`。
- Pocket2Mol 工具包能消费标准 `binding_pocket@1`。
- Agent / workflow 不再要求手动输入语义映射。
- 旧工具仍可运行，旧字段只作为兼容路径存在。
