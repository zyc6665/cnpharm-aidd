# 标准 Artifact 驱动边界设计

## 1. 目标

平台最难扩展的部分不是新增一个模型工具，而是新增工具后，工具详情页、节点独立运行、工作流运行和 Agent 计划仍然能用同一套规则完成输入绑定、预检、运行、结果持久化和可视化。

本设计把 Standard Artifact 作为平台编排的核心契约。工作流不能依赖文件名、扩展名、工具私有字段或 executor 细节；它只能依赖 Tool Contract 中声明的 Artifact Slot，以及 Run Preparation 对 ArtifactVersion 的绑定决策。

核心目标：

- 新工具只要声明标准 Artifact 输入输出，就能被工作流发现和预检。
- 工作流连线只表达标准 Artifact 语义，不表达文件路径。
- Run Preparation 能区分缺输入、类型不匹配、版本不兼容、role 缺失、需要处理、需要转换、需要选择、权限不足和上游未完成。
- 新 Artifact 类型、新 role、新 renderer、新 executor 可以扩展，但不会破坏旧工作流。

## 2. 核心判断

标准 Artifact 不能只等于 `protein_structure@1` 这样的类型名。真正可编排的 Artifact 必须由以下维度共同决定：

```text
Standard Artifact usability
  = type ref
  + version compatibility
  + file roles
  + metadata schema
  + readiness state
  + cardinality
  + lineage
  + validation status
  + permission scope
```

如果平台只看 `type`，就会出现这些错误：

- 原始 PDB 被直接送去需要 `receptor_pdbqt` 的对接工具。
- 只有 2D SDF 的配体被送去 3D docking。
- molecule table 没有 SMILES 列却被送去 ADMET。
- 多个 pocket 输出被自动送到只接受单 pocket 的工具。
- 保存工作流加载后拿到过期 ArtifactVersion，却仍然显示可运行。

## 3. 标准 Artifact 可用性模型

### 3.1 Type Ref

`type@version` 是最粗粒度的语义匹配。

示例：

- `protein_structure@1`
- `ligand_structure@1`
- `binding_pocket@1`
- `molecule_table@1`

规则：

- 工具契约必须使用带版本 ref。
- 工作流边必须记录 source slot 和 target slot，而不是只记录类型字符串。
- 类型不匹配时直接返回 `invalid_type`。

### 3.2 Version Compatibility

版本兼容不能默认成立。

工具输入 slot 应支持：

```yaml
accepted_versions: [1]
version_policy: exact
```

可选策略：

| 策略 | 含义 |
| --- | --- |
| `exact` | 只接受声明版本 |
| `compatible_minor` | 接受同类型兼容版本 |
| `upgrade_with_tool` | 需要插入升级工具 |
| `reject` | 不兼容 |

第一版可以只实现 `exact`，但契约字段要预留，避免未来 `protein_structure@2` 出现时只能靠硬编码兼容。

### 3.3 File Roles

role 是 ArtifactVersion 中具体文件的语义，不是文件名。

输入 slot 应声明：

```yaml
required_roles: [receptor_pdbqt]
role_preferences: [prepared_pdb, structure_file]
```

规则：

- `required_roles` 缺失时返回 `invalid_role` 或 `needs_preparation`。
- `role_preferences` 只影响选择顺序，不能替代 required role。
- ArtifactVersion 可以包含多个 role，但每个 role 的含义必须由 registry 定义。
- 新 role 优先扩展已有类型；只有语义对象变化时才新增 Artifact type。

### 3.4 Metadata Schema

metadata 表达 role 之外的科学状态。

示例：

- `protein_structure@1`: `preparation_status`、`ph`、`chain_ids`、`remove_water`。
- `ligand_structure@1`: `structure_3d_source`、`hydrogens_added`、`stereochemistry_undefined`。
- `molecule_table@1`: `molecule_id_field`、`columns`、`smiles_field`。
- `binding_pocket@1`: `center`、`bbox`、`source_protein_ref`。

规则：

- 必填 metadata 缺失时，ArtifactVersion 不能进入 `available`。
- 下游工具可以声明 metadata 条件。
- metadata 条件不满足时返回 `invalid_metadata`、`needs_preparation` 或 `needs_conversion`。

### 3.5 Readiness State

readiness 表示“这个 ArtifactVersion 是否满足某个下游 slot”。它不是 Artifact 全局状态，而是相对于工具输入 slot 的判断。

常见 readiness policy：

| policy | 含义 | 示例 |
| --- | --- | --- |
| `allow_raw` | 原始输入可直接用 | 文件查看、轻量检查 |
| `prefer_prepared_warn_raw` | 优先准备态，原始态可运行但警告 | LVpocket |
| `require_prepared` | 必须准备态 | 高质量结构建模 |
| `require_receptor` | 必须具备 receptor role | Docking |
| `prefer_3d_ligand` | 优先 3D 配体，缺失时建议构象生成 | Docking / shape model |
| `require_columns` | 表格必须具备指定列 | ADMET / scoring |

规则：

- readiness 由 Run Preparation 计算。
- readiness 不应写死在 workflow scheduler。
- readiness 失败要给出下一步动作：上传、选择、插入准备工具、插入转换工具、等待上游或联系管理员。

### 3.6 Cardinality

cardinality 表示 slot 接受一个、多个还是集合。

```yaml
cardinality: one | many | table | collection
```

规则：

- 上游输出 many，下游输入 one 时，必须有选择规则，否则返回 `ambiguous_binding`。
- 上游输出 one，下游输入 many 时，可以自动包装为单元素集合。
- table 不等于 many files；table 需要 column schema。
- 工作流未来的 map/batch 节点必须基于 cardinality，而不是基于工具名。

### 3.7 Validation Status

ArtifactVersion 必须有验证状态：

```text
pending -> validating -> available
                      -> invalid
                      -> failed
                      -> deprecated
                      -> expired
```

规则：

- 只有 `available` 可默认绑定。
- `deprecated` 可允许手动选择，但必须警告。
- `expired`、`invalid`、`failed` 不能绑定。
- 保存工作流中的旧 ArtifactVersion 若不可用，应返回 `stale_binding`。

### 3.8 Permission Scope

ArtifactVersion 绑定必须受 Run Context 约束。

规则：

- 选择已有 ArtifactVersion 必须有项目上下文或默认工作空间权限。
- 跨项目不能直接绑定。
- 跨项目复用应显式复制/导入，生成新的 Artifact 或 ArtifactVersion，并保留 lineage。
- 工作流保存的 ArtifactVersion ID 加载时必须重新校验权限。

### 3.9 Lineage

lineage 表示 ArtifactVersion 之间的科学关系。

规则：

- 处理、转换、打分、筛选都应生成新的 ArtifactVersion 或新的 Artifact。
- 下游工具不能静默改写上游 ArtifactVersion。
- `derived_from`、`contains`、`describes`、`ranked_by`、`validated_by` 等关系必须指向 ArtifactVersion。
- 谱系不能跨项目直接建立，跨项目复制后再建立新关系。

## 4. Artifact Slot 契约

Tool Contract 的 Artifact Slot 是新工具能否自动进入工作流的关键。

### 4.1 Input Slot

建议结构：

```yaml
artifacts:
  inputs:
    - name: receptor
      type: protein_structure@1
      accepted_versions: [1]
      required: true
      cardinality: one
      required_roles: [receptor_pdbqt]
      role_preferences: [receptor_pdbqt]
      readiness_policy: require_receptor
      suggested_preparation_tool: builtin-protein-preparation
      metadata_requirements:
        preparation_status: prepared
```

字段含义：

| 字段 | 作用 |
| --- | --- |
| `name` | 工具内部稳定 slot 名 |
| `type` | 标准 Artifact ref |
| `accepted_versions` | 可接受版本 |
| `required` | 是否必填 |
| `cardinality` | one/many/table/collection |
| `required_roles` | 必须具备的文件角色 |
| `role_preferences` | 可用 role 选择顺序 |
| `readiness_policy` | 输入准备状态策略 |
| `suggested_preparation_tool` | 准备/转换工具建议 |
| `metadata_requirements` | metadata 条件 |
| `column_requirements` | 表格列条件 |

### 4.2 Output Slot

建议结构：

```yaml
artifacts:
  outputs:
    - name: pockets
      type: binding_pocket@1
      cardinality: many
      required: true
      provided_roles: [residue_pocket_pdb, atom_pocket_pdb, pocket_metadata_json]
      ranking:
        score_field: confidence
        order: desc
      lineage:
        relation: derived_from
        input_slot: protein
```

规则：

- output slot 必须声明 type 和 cardinality。
- `provided_roles` 应覆盖结果 manifest 中实际可生成的 role。
- many 输出应声明 ranking 或 selection hint，方便下游 one 输入选择。
- required output 缺失时，Task 不能标记为成功的标准 Artifact 运行。

## 5. BindingDecision 状态机

Run Preparation 对每个 input slot 输出 BindingDecision。

```text
missing
  ├─ waiting_upstream
  ├─ ready
  ├─ needs_selection
  ├─ needs_preparation
  ├─ needs_conversion
  ├─ invalid_type
  ├─ incompatible_version
  ├─ invalid_role
  ├─ invalid_metadata
  ├─ invalid_columns
  ├─ stale_binding
  └─ permission_denied
```

状态含义：

| 状态 | 含义 | 用户动作 |
| --- | --- | --- |
| `ready` | 可运行 | 无 |
| `missing` | 无输入来源 | 连接上游、选择 Artifact 或上传 |
| `waiting_upstream` | 上游节点未完成 | 先运行上游 |
| `needs_selection` | 多个候选无法自动选择 | 选择一个候选 |
| `needs_preparation` | 需要清理、加氢、质子化等处理 | 插入准备工具 |
| `needs_conversion` | 需要格式或维度转换 | 插入转换工具 |
| `invalid_type` | Artifact type 不匹配 | 更换连接或工具 |
| `incompatible_version` | 版本不兼容 | 升级/降级 Artifact |
| `invalid_role` | required role 缺失 | 准备/转换或换输入 |
| `invalid_metadata` | metadata 条件不满足 | 准备/换输入 |
| `invalid_columns` | 表格列不满足 | 映射列或换表格 |
| `stale_binding` | 保存绑定已过期或不可用 | 重新绑定 |
| `permission_denied` | 无权限访问 | 切项目或申请权限 |

禁止把这些状态合并成泛化的“工具契约不可执行”或“节点任务失败”。

## 6. Workflow 连接规则

### 6.1 Edge 语义

工作流边连接的是 slot，不是文件：

```text
source_node.output_slot -> target_node.input_slot
```

边可以保存：

```yaml
edge:
  source: node_a
  source_output: protein
  target: node_b
  target_input: receptor
  artifact_type: protein_structure@1
  binding_intent:
    selected_role: receptor_pdbqt
    selection_policy: top_ranked
```

规则：

- edge 的 source_output 和 target_input 必须存在于当前 Tool Contract 或 snapshot。
- type 不匹配不能连接。
- role 不满足可以连接但预检必须给出 preparation/conversion 建议。
- 多输出连接到单输入时必须有选择策略。

### 6.2 Workflow Input Promotion

必填 input slot 没有上游来源时，应提升为 Workflow Input。

```text
tool input slot -> workflow input requirement
```

规则：

- Workflow Input 保留原 input slot 的 type、roles、metadata、cardinality 要求。
- 用户上传文件或选择 Artifact 后，仍必须通过 Run Preparation 校验。
- Workflow Input 不应变成普通文件字段。

### 6.3 Saved Workflow Hydration

保存工作流时需要保存：

- `tool_slug`
- `tool_version_id` 或 `contract_version`
- `contract_snapshot`
- nodes / edges
- workflow inputs
- Node Task Binding
- ArtifactVersion bindings

加载时规则：

1. 优先读取当前 Tool Contract。
2. 如果当前 contract 可兼容旧 snapshot，则 hydrate 缺失槽位。
3. 如果不兼容，保留旧 snapshot 并提示重新预检。
4. 如果工具被禁用，节点可展示但不可运行。
5. 如果 ArtifactVersion 失效，返回 `stale_binding`。

## 7. 新工具接入边界

新工具要自动兼容工作流，必须满足：

1. Tool Contract 校验通过。
2. input/output slots 使用标准 Artifact ref。
3. 输入 slot 声明 cardinality、roles、readiness policy。
4. 输出 slot 声明 cardinality、provided_roles、result manifest 映射。
5. smoke example 能生成或消费标准 Artifact。
6. 资源画像和 executor 明确。
7. 无需新增工作流专属适配代码。

如果一个新模型只能说“传一个文件进去，返回一个 zip”，它还不能作为标准工作流工具发布，只能作为 legacy 工具或待封装工具。

## 8. 边界场景清单

### 8.1 类型与 role

| 场景 | 期望 |
| --- | --- |
| Fetch PDB 输出 raw protein，LVpocket 输入 protein | `ready` + preparation warning |
| Fetch PDB 输出 raw protein，Docking 输入 receptor | `needs_preparation` |
| Ligand 只有 2D，Docking 输入 ligand | `needs_conversion` |
| Pocket 输出 PDB 文件但缺 `pocket_metadata_json` | `invalid_role` |
| Tool 输出未注册 Artifact type | contract validation failed |

### 8.2 metadata 与表格列

| 场景 | 期望 |
| --- | --- |
| molecule table 缺 SMILES 列，ADMET 输入 molecules | `invalid_columns` |
| molecule table 有多个候选 ID 字段 | `needs_selection` 或 column mapping |
| protein metadata 缺 chain_ids | artifact validation failed |
| pocket metadata 缺 center/bbox，Docking 需要 box | `invalid_metadata` |
| ligand stereochemistry undefined，模型要求明确手性 | `invalid_metadata` |

### 8.3 cardinality

| 场景 | 期望 |
| --- | --- |
| LVpocket 输出 many pockets，Molecule Generation 输入 one pocket | `needs_selection` 或按 ranking 自动选 |
| one ligand 输入 many ligands slot | 自动包装为单元素集合 |
| molecule table 输入 single-ligand docking | 需要 map/batch 策略 |
| Docking 输出 many poses，Scoring 输入 table | 需要 pose-to-table 转换或 docking score table |

### 8.4 version 与 contract 升级

| 场景 | 期望 |
| --- | --- |
| 工具接受 `protein_structure@1`，上游是 `protein_structure@2` | `incompatible_version` 或 upgrade policy |
| 保存工作流的 output slot 被新 Tool Contract 改名 | 使用 snapshot，提示重新预检 |
| 新 tool version 删除 required output | contract validation failed 或 breaking change |
| Artifact type 新增 required role | 需要迁移策略，不直接破坏旧 ArtifactVersion |

### 8.5 permission 与生命周期

| 场景 | 期望 |
| --- | --- |
| 项目 A Artifact 被项目 B 工作流绑定 | `permission_denied` 或显式导入 |
| 保存绑定的 ArtifactVersion 已 expired | `stale_binding` |
| 上游 task failed 但有普通输出文件 | 下游等待或 blocked，不自动作为 Standard Artifact |
| Remote API result manifest checksum 不匹配 | collect failed，不创建 ArtifactVersion |
| 用户取消长任务后有半成品轨迹 | 可作为 TaskOutput 附件，不是 available Artifact |

### 8.6 workflow 与 Agent

| 场景 | 期望 |
| --- | --- |
| Agent 生成 workflow 使用不存在的 slot | preflight invalid，不能运行 |
| 工作流边连接同 type 但 target required role 不满足 | edge 可存在，preflight 提示处理节点 |
| 用户手动选择 input 覆盖上游默认绑定 | 显式选择优先，记录 override |
| 多个上游都能满足同一 slot | `needs_selection`，除非有明确优先级 |
| 工具禁用后加载旧 workflow | 节点可展示，不可运行，保留历史结果 |

## 9. Run Preparation Interface 要求

Run Preparation 应提供两个层次的接口：

```text
preview(input) -> ReadinessReport
prepare(input) -> PreparedRun | PreparationError
```

区别：

- `preview` 用于前端预检，可缺少实际 staged 文件。
- `prepare` 用于后端权威运行准备，必须做权限、存在性、role、metadata、生命周期和 legacy 投影校验。

PreparedRun 必须包含：

- normalized params。
- selected file IDs。
- input bindings。
- staged standard uploads。
- binding decisions。
- output project decision。
- execution input manifest。
- lineage seed。

## 10. 禁止事项

- 禁止 workflow scheduler 直接读取文件 role 并做绑定决策。
- 禁止工具详情页构造最终 `input_bindings` / `standard_input_uploads` 内部字段。
- 禁止用文件扩展名替代 Artifact role。
- 禁止将 `molecule_table@1` 当作任意 CSV 表格。
- 禁止把多语义结果塞进一个 generic Artifact。
- 禁止新工具要求工作流新增专属适配。
- 禁止下游工具静默改写上游 ArtifactVersion。
- 禁止把 executor 类型作为工作流连线语义。

## 11. 第一阶段落地范围

第一阶段只做足以保护平台可扩展性的核心闭环：

1. 固化 Artifact Slot 字段：type、accepted_versions、required_roles、role_preferences、readiness_policy、cardinality。
2. 固化 BindingDecision 状态机。
3. Run Preparation 成为工具详情页、节点独立运行、工作流运行的唯一权威。
4. 工作流边改为 source output slot 到 target input slot。
5. 保存工作流必须保存 contract snapshot 和 Node Task Binding。
6. 新工具发布必须通过 Artifact Slot contract validation。

暂缓：

- 复杂自动编排。
- 跨项目自动共享。
- 自动版本升级。
- 通用 map/batch 引擎。
- 大规模迁移所有历史 workflow。
