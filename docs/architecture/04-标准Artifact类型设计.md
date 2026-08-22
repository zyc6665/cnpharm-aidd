# 标准 Artifact 类型设计

## 1. 设计目标

标准 Artifact 是平台的数据主线。它用于把“文件”提升为平台可理解、可校验、可复用、可视化和可编排的科研资产。

标准 Artifact 设计要解决四个问题：

1. 工具之间如何交接数据。
2. 工作流如何自动绑定上下游。
3. 结果如何可视化和下载。
4. 数据如何形成可追踪谱系。

## 2. 基本模型

```text
StandardArtifactSpec
 ├─ type: protein_structure
 ├─ version: 1
 ├─ ref: protein_structure@1
 ├─ file_roles[]
 ├─ metadata_schema
 └─ validators[]

Artifact
 ├─ project_id
 ├─ standard_type
 ├─ standard_version
 ├─ source_task_id
 └─ latest_version_id

ArtifactVersion
 ├─ artifact_id
 ├─ manifest_json
 ├─ summary_json
 ├─ metrics_json
 ├─ validation_status
 └─ files[]

ArtifactVersionFile
 ├─ artifact_version_id
 ├─ role
 ├─ file_id
 ├─ is_primary
 └─ sort_order
```

## 3. 命名规则

### 3.1 标准类型 ref

格式：

```text
<type>@<version>
```

示例：

- `protein_structure@1`
- `ligand_structure@1`
- `binding_pocket@1`
- `molecule_table@1`
- `run_report@1`

规则：

- `type` 使用小写 snake_case。
- `version` 使用整数。
- 新版本只能新增兼容字段或明确迁移策略。
- 工作流和工具契约必须使用带版本 ref。

### 3.2 文件角色

文件角色表示一个 ArtifactVersion 内部文件的语义，不是文件名。

示例：

- `structure_file`
- `metadata_json`
- `prepared_pdb`
- `receptor_pdbqt`
- `residue_pocket_pdb`
- `table_file`

规则：

- role 使用小写 snake_case。
- 每个标准类型必须有一个 primary role。
- required role 缺失时 ArtifactVersion 不应标记为 available。
- 文件名可变，role 不应变。

## 4. 当前标准类型

### 4.1 `protein_structure@1`

用途：表示蛋白结构及其处理状态。

必需角色：

| role | 说明 | 格式 |
| --- | --- | --- |
| `structure_file` | 主结构文件 | pdb |
| `metadata_json` | 结构元数据 | json |

可选角色：

| role | 说明 | 格式 |
| --- | --- | --- |
| `raw_structure_file` | 原始下载或上传结构 | pdb, cif |
| `prepared_pdb` | 去水、加氢等处理后的 PDB | pdb |
| `prepared_pqr` | PQR 格式 | pqr |
| `receptor_pdbqt` | 对接所需 receptor PDBQT | pdbqt |
| `preparation_report_json` | 蛋白处理报告 | json |

核心元数据：

- chain_ids。
- residue_count。
- atom_count。
- structure_format。
- source_filename。
- source_database。
- source_id。
- preparation_status。
- preparation_profile。
- ph。
- remove_water。
- keep_metals。
- keep_cofactors。

设计说明：

- 未处理 PDB 和处理后 PDB 不应混为同一角色。
- LVpocket 这类口袋预测工具可以声明 `role_preferences: [prepared_pdb, structure_file]`。
- Vina / Smina 对接工具应优先要求 `receptor_pdbqt`，不足时提示蛋白处理节点。

### 4.2 `ligand_structure@1`

用途：表示小分子结构，支持 2D 和 3D。

必需角色：

| role | 说明 | 格式 |
| --- | --- | --- |
| `structure_file` | 主结构文件 | sdf |

可选角色：

| role | 说明 | 格式 |
| --- | --- | --- |
| `structure_2d_sdf` | 2D 构象 | sdf |
| `structure_3d_sdf` | 3D 构象 | sdf |
| `metadata_json` | 配体元数据 | json |

核心元数据：

- ligand_id。
- source_database。
- source_id。
- pubchem_cid。
- canonical_smiles。
- isomeric_smiles。
- molecular_formula。
- molecular_weight。
- structure_3d_source。
- hydrogens_added。
- stereochemistry_undefined。

设计说明：

- PubChem 无 3D 时，可以通过 RDKit 生成 `structure_3d_sdf`。
- 2D 和 3D 不应做成两个标准类型，应该是同一个 ligand Artifact 的不同角色。
- 对接工具可声明 `role_preferences: [structure_3d_sdf, structure_file]`。

### 4.3 `binding_pocket@1`

用途：表示口袋预测结果。

必需角色：

| role | 说明 | 格式 |
| --- | --- | --- |
| `residue_pocket_pdb` | 残基层面的口袋结构 | pdb |
| `atom_pocket_pdb` | 原子层面的口袋结构 | pdb |
| `pocket_metadata_json` | 口袋中心、包围盒、残基和原子列表 | json |

核心元数据：

- center。
- bbox。
- residue_ids。
- atom_ids。
- source_protein_ref。

设计说明：

- 口袋不是普通 PDB 文件，它必须包含口袋空间和来源蛋白信息。
- 下游分子生成、对接盒子生成、可视化都应消费该标准类型。

### 4.4 `molecule_table@1`

用途：表示分子列表、分子属性表、候选分子集合或筛选结果表。

必需角色：

| role | 说明 | 格式 |
| --- | --- | --- |
| `table_file` | 分子表 | csv, json |
| `metadata_json` | 表结构和来源说明 | json |

核心元数据：

- molecule_id_field。
- source_task_id。

设计说明：

- ADMET、毒性、合成可及性和打分重排可复用该类型。
- 如果后续需要区分“候选表”和“评分表”，优先通过 metadata 和 column schema 表达，必要时再升版本或新增类型。

### 4.5 `run_report@1`

用途：表示工具运行报告、质量检查报告和解释性结果。

必需角色：

| role | 说明 | 格式 |
| --- | --- | --- |
| `report_json` | 机器可读报告 | json |

可选角色：

| role | 说明 | 格式 |
| --- | --- | --- |
| `report_markdown` | 人类可读报告 | md |

核心元数据：

- source_task_id。

设计说明：

- 蛋白处理、对接、MD、批量筛选都可以额外输出 run_report。
- 报告不替代核心结构或表格 Artifact。

## 5. 建议新增类型

### 5.1 `docking_pose@1`

用途：表示对接后复合物或配体 pose。

建议角色：

| role | required | 说明 |
| --- | --- | --- |
| `pose_sdf` | true | 配体 pose |
| `pose_pdbqt` | false | 对接输出 PDBQT |
| `complex_pdb` | false | 蛋白-配体复合物 |
| `score_json` | true | 打分和对接参数 |
| `metadata_json` | true | 来源、box、工具版本 |

### 5.2 `docking_score_table@1`

用途：表示批量对接或重排结果。

建议角色：

| role | required | 说明 |
| --- | --- | --- |
| `score_table` | true | CSV/JSON 排名表 |
| `metadata_json` | true | scoring 函数、box、输入来源 |

### 5.3 `md_trajectory@1`

用途：表示分子动力学轨迹。

建议角色：

| role | required | 说明 |
| --- | --- | --- |
| `topology_file` | true | 拓扑文件 |
| `trajectory_file` | true | 轨迹文件 |
| `summary_json` | true | RMSD、RMSF、能量摘要 |
| `metadata_json` | true | 力场、水模型、温度、步长 |

### 5.4 `admet_report@1`

用途：表示 ADMET 预测结果。

建议角色：

| role | required | 说明 |
| --- | --- | --- |
| `prediction_table` | true | 分子级预测表 |
| `summary_json` | true | 指标摘要 |
| `metadata_json` | true | 模型版本、阈值、输入来源 |

### 5.5 `toxicity_report@1`

用途：表示毒性预测结果。

建议角色同 `admet_report@1`，但 metadata 应包含 endpoint、species、assay family 等字段。

## 6. Artifact 生命周期

```text
created
  ▼
validating
  ▼
available ──► deprecated
  │
  └──────► failed
```

第一版可继续使用现有 `available` / validation 字段，但 UI 和服务应逐步按生命周期表达。

## 7. Artifact 来源

| 来源 | 示例 | 处理方式 |
| --- | --- | --- |
| 用户上传 | 上传 PDB/SDF/CSV | 进入项目或默认工作空间后建 Artifact |
| 外部数据库 | PDB、PubChem | 记录 source_database、source_id、source_url |
| 工具输出 | LVpocket、RDKit、Vina | 记录 source_task_id 和 ToolVersion |
| 工作流输出 | 上游节点产物 | 记录 WorkflowRun 和 Node |
| Agent 触发 | Agent 计划执行 | 仍通过 Task 和 Tool 产生 |

## 8. 谱系关系

当前关系类型：

- `derived_from`
- `contains`
- `describes`
- `ranked_by`
- `validated_by`
- `visualized_by`

推荐使用方式：

| 关系 | 示例 |
| --- | --- |
| `derived_from` | prepared protein derived from raw protein |
| `contains` | molecule table contains ligand structures |
| `describes` | run report describes docking run |
| `ranked_by` | ligand set ranked_by docking score table |
| `validated_by` | protein validated_by preparation report |
| `visualized_by` | pocket visualized_by viewer state |

## 9. 工作流绑定规则

工作流绑定只看标准 Artifact ref 和 slot 约束：

1. 上游 `artifacts.outputs[].type` 匹配下游 `artifacts.inputs[].type`。
2. 如果下游声明 `required_roles`，上游 ArtifactVersion 必须具备这些 role。
3. 如果下游声明 `role_preferences`，Binding Resolver 优先选择这些 role。
4. 如果 role 不满足但有 `suggested_preparation_tool`，预检提示插入处理节点。
5. 如果无上游且必填，则提升为工作流输入。

## 10. 可视化规则

| Artifact type | 默认渲染器 | 备用渲染器 |
| --- | --- | --- |
| `protein_structure@1` | Protein Renderer | File Renderer |
| `ligand_structure@1` | Ligand Renderer | Molecule/File Renderer |
| `binding_pocket@1` | Pocket Renderer | Protein Renderer |
| `molecule_table@1` | Table Renderer | File Renderer |
| `run_report@1` | Report Renderer | JSON/Markdown Renderer |

渲染器只依赖 Artifact 类型和文件角色，不依赖具体工具 slug。

## 11. 版本治理

新增或升级标准类型时必须回答：

- 是否能兼容旧工具。
- 是否影响工作流自动绑定。
- 是否需要迁移已有 Artifact。
- 是否需要新增渲染器。
- 是否需要新增 Binding Resolver 规则。
- 是否需要新增外部数据库导入规则。

## 12. 禁止事项

- 禁止用工具 slug 判断 Artifact 类型。
- 禁止让工作流边绑定物理文件路径。
- 禁止把多个不同语义结果塞进一个 generic file。
- 禁止在工具参数 schema 中重复声明标准 Artifact 文件输入。
- 禁止跨项目建立 Artifact 谱系。
