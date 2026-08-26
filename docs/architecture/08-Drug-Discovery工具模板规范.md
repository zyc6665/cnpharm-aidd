# Drug Discovery 工具模板规范

## 1. 目标

药物研发工具模板用于把外部数据库、传统 CADD 工具、平台内置轻量工具和深度学习模型统一成可注册、可运行、可编排、可视化的工具能力。新增工具不应再靠前端或工作流单独适配，而应通过 Tool Contract、标准 Artifact 和 Resource Profile 自动进入工具库、工作流和智能体上下文。

第一版目标：

- 覆盖外部数据库、蛋白处理、配体处理、口袋预测、分子生成、ADMET、毒性、合成可及性、构象生成、分子对接、MD 和打分重排。
- 允许每类工具独立运行、项目内运行和工作流运行。
- 轻量工具可以平台内置，重计算工具必须通过执行器和资源画像调度。
- 不引入“多实现变体”概念；Docker、SSH、Remote API、K8s、Slurm 是执行方式，不是研发语义上的不同工具类型。

## 2. 模板设计原则

1. 工具模板描述研发能力，不描述某台机器或某个部署环境。
2. 工具输入输出优先使用标准 Artifact Slot。
3. 普通参数只放到 `parameters_schema`。
4. 数据准备要求通过 `required_roles`、`role_preferences` 和 `readiness_policy` 声明。
5. 计算资源通过 `resource_profile` 声明。
6. 执行方式通过 `executor.type` 声明。
7. 可视化由 Artifact Renderer 决定，不由工具私有 UI 决定。

## 3. 通用模板骨架

```yaml
metadata:
  slug: <stable-tool-slug>
  name: <display name>
  version: 1.0.0
  description: <scientific purpose>
category:
  domain: drug_discovery
  stage: <fetch|prepare|predict|generate|dock|simulate|score|report>
  tags: [<admin-managed-tags>]
exposure:
  direct_run: true
  workflow: true
  agent: true
parameters_schema:
  type: object
  properties: {}
artifacts:
  inputs: []
  outputs: []
resource_profile:
  tier: cpu-small
  cpu: 2
  memory_gb: 4
  gpu_required: false
  expected_minutes: 2
  timeout_minutes: 15
executor:
  type: builtin
examples:
  - name: smoke
    smoke: true
    parameters: {}
```

## 4. 外部数据库查询模板

### 4.1 Fetch PDB

用途：通过 PDB ID 或查询条件获取蛋白结构。

```yaml
metadata:
  slug: builtin-fetch-pdb
parameters_schema:
  type: object
  required: [pdb_id]
  properties:
    pdb_id:
      type: string
      pattern: "^[0-9A-Za-z]{4}$"
artifacts:
  outputs:
    - name: protein
      type: protein_structure@1
      cardinality: one
      required: true
      provided_roles: [structure_file, metadata_json, raw_structure_file]
resource_profile:
  tier: network-small
  cpu: 1
  memory_gb: 1
  gpu_required: false
executor:
  type: builtin
```

工作流行为：输出可直接连接蛋白处理、口袋预测或结构查看；如果下游要求 `prepared_pdb` 或 `receptor_pdbqt`，Run Preparation 应基于 Artifact Binding 决策提示插入蛋白处理节点。

### 4.2 Fetch PubChem Ligand

用途：通过 CID、名称或 SMILES 获取小分子结构。

```yaml
metadata:
  slug: builtin-fetch-pubchem-ligand
parameters_schema:
  type: object
  properties:
    query:
      type: string
    query_type:
      type: string
      enum: [cid, name, smiles]
artifacts:
  outputs:
    - name: ligand
      type: ligand_structure@1
      cardinality: one
      required: true
      provided_roles: [structure_file, structure_2d_sdf, structure_3d_sdf, metadata_json]
resource_profile:
  tier: network-small
executor:
  type: builtin
```

第一版要求同时支持 2D 和 3D。若上游数据库没有 3D，平台内置 RDKit 可补 3D 并在 metadata 中记录 `structure_3d_source=rdkit_generated`。

## 5. 蛋白处理模板

用途：将原始蛋白结构转换为下游可用的准备态蛋白，例如去水、去非目标配体、加氢、质子化状态处理和格式转换。

```yaml
metadata:
  slug: builtin-protein-preparation
parameters_schema:
  type: object
  properties:
    ph:
      type: number
      default: 7.4
    remove_water:
      type: boolean
      default: true
    keep_metals:
      type: boolean
      default: true
    keep_cofactors:
      type: boolean
      default: true
    remove_non_target_ligands:
      type: boolean
      default: true
    output_formats:
      type: array
      items:
        type: string
        enum: [pdb, pqr, pdbqt]
artifacts:
  inputs:
    - name: protein
      type: protein_structure@1
      required: true
      role_preferences: [structure_file, raw_structure_file]
  outputs:
    - name: prepared_protein
      type: protein_structure@1
      cardinality: one
      required: true
      provided_roles: [structure_file, prepared_pdb, prepared_pqr, receptor_pdbqt, preparation_report_json]
resource_profile:
  tier: cpu-small
executor:
  type: builtin
```

设计说明：

- 该工具是工作过程的一部分，应作为画布节点显示。
- 下游工具不应自己静默清理蛋白；如果缺少所需 role，应由预检提示或建议插入该节点。
- 后续可将具体引擎从内置升级为 Docker、SSH 或 K8s，但 Tool Contract 不变。

## 6. 配体处理和构象生成模板

### 6.1 Ligand Preparation

用途：标准化小分子结构、加氢、生成 3D、转格式。

```yaml
metadata:
  slug: builtin-ligand-preparation
parameters_schema:
  type: object
  properties:
    ph:
      type: number
      default: 7.4
    generate_3d:
      type: boolean
      default: true
    output_formats:
      type: array
      items:
        type: string
        enum: [sdf, mol2, pdbqt]
artifacts:
  inputs:
    - name: ligand
      type: ligand_structure@1
      required: true
      role_preferences: [structure_3d_sdf, structure_file, structure_2d_sdf]
  outputs:
    - name: prepared_ligand
      type: ligand_structure@1
      cardinality: one
      required: true
      provided_roles: [structure_file, structure_3d_sdf, metadata_json]
resource_profile:
  tier: cpu-small
executor:
  type: builtin
```

### 6.2 Conformer Generation

用途：为对接、构象筛选或后续打分生成构象集合。

```yaml
metadata:
  slug: builtin-conformer-generation
parameters_schema:
  type: object
  properties:
    max_conformers:
      type: integer
      default: 20
    forcefield:
      type: string
      enum: [uff, mmff94]
artifacts:
  inputs:
    - name: ligand
      type: ligand_structure@1
      required: true
      role_preferences: [structure_3d_sdf, structure_file]
  outputs:
    - name: conformers
      type: ligand_structure@1
      cardinality: many
      required: true
      provided_roles: [structure_3d_sdf, metadata_json]
resource_profile:
  tier: cpu-small
executor:
  type: builtin
```

## 7. RDKit 分子属性模板

用途：计算传统 CADD 分子属性、Lipinski 指标、简单过滤和描述符。第一版可平台内置，同时作为节点工具使用。

```yaml
metadata:
  slug: builtin-rdkit-properties
parameters_schema:
  type: object
  properties:
    descriptors:
      type: array
      items:
        type: string
artifacts:
  inputs:
    - name: molecules
      type: ligand_structure@1
      required: true
      role_preferences: [structure_file, structure_2d_sdf, structure_3d_sdf]
  outputs:
    - name: property_table
      type: molecule_table@1
      cardinality: one
      required: true
      provided_roles: [table_file, metadata_json]
resource_profile:
  tier: cpu-small
executor:
  type: builtin
```

注意：RDKit 工具和深度学习 ADMET 是不同工具，因为研发语义不同。二者都可以进入工作流，用户按任务目标选择。

## 8. 口袋预测模板

用途：从蛋白结构预测潜在结合口袋。

```yaml
metadata:
  slug: lvpocket-pocket-prediction
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
      provided_roles: [residue_pocket_pdb, atom_pocket_pdb, pocket_metadata_json]
resource_profile:
  tier: cpu-medium
executor:
  type: ssh_job
```

如果上游来自 Fetch PDB，预检应提示“原始蛋白可运行但建议先 Protein Preparation”；如果工具明确要求 prepared role，则应阻断并建议插入处理节点。

## 9. 分子生成模板

用途：基于蛋白、口袋或种子分子生成候选小分子。

```yaml
metadata:
  slug: molecule-generation
parameters_schema:
  type: object
  properties:
    num_molecules:
      type: integer
      default: 32
    temperature:
      type: number
      default: 1.0
artifacts:
  inputs:
    - name: pocket
      type: binding_pocket@1
      required: false
      role_preferences: [pocket_metadata_json, residue_pocket_pdb]
    - name: seed_ligand
      type: ligand_structure@1
      required: false
      role_preferences: [structure_3d_sdf, structure_file]
  outputs:
    - name: candidates
      type: molecule_table@1
      cardinality: one
      required: true
      provided_roles: [table_file, metadata_json]
resource_profile:
  tier: gpu-medium
  gpu_required: true
executor:
  type: remote_api
```

## 10. ADMET、毒性和合成可及性模板

### 10.1 ADMET Prediction

```yaml
metadata:
  slug: admet-prediction
artifacts:
  inputs:
    - name: molecules
      type: molecule_table@1
      required: true
      role_preferences: [table_file]
  outputs:
    - name: admet_table
      type: molecule_table@1
      cardinality: one
      required: true
      provided_roles: [table_file, metadata_json]
    - name: report
      type: run_report@1
      cardinality: one
      required: false
      provided_roles: [report_json, report_markdown]
resource_profile:
  tier: gpu-small
executor:
  type: remote_api
```

### 10.2 Toxicity Prediction

```yaml
metadata:
  slug: toxicity-prediction
artifacts:
  inputs:
    - name: molecules
      type: molecule_table@1
      required: true
      role_preferences: [table_file]
  outputs:
    - name: toxicity_table
      type: molecule_table@1
      cardinality: one
      required: true
      provided_roles: [table_file, metadata_json]
resource_profile:
  tier: gpu-small
executor:
  type: remote_api
```

### 10.3 Synthetic Accessibility

```yaml
metadata:
  slug: synthetic-accessibility
artifacts:
  inputs:
    - name: molecules
      type: molecule_table@1
      required: true
      role_preferences: [table_file]
  outputs:
    - name: sa_table
      type: molecule_table@1
      cardinality: one
      required: true
      provided_roles: [table_file, metadata_json]
resource_profile:
  tier: cpu-small
executor:
  type: builtin
```

第一版可复用 `molecule_table@1` 输出。后续如果需要更强语义，可新增 `admet_report@1`、`toxicity_report@1`。

## 11. 分子对接模板

用途：将准备好的 receptor 和 ligand 进行 docking，产出 pose 和 score。

```yaml
metadata:
  slug: molecular-docking
parameters_schema:
  type: object
  properties:
    exhaustiveness:
      type: integer
      default: 8
    num_modes:
      type: integer
      default: 9
artifacts:
  inputs:
    - name: receptor
      type: protein_structure@1
      required: true
      required_roles: [receptor_pdbqt]
      role_preferences: [receptor_pdbqt]
      readiness_policy: require_prepared
      suggested_preparation_tool: builtin-protein-preparation
    - name: ligand
      type: ligand_structure@1
      required: true
      role_preferences: [structure_3d_sdf, structure_file]
    - name: pocket
      type: binding_pocket@1
      required: false
      role_preferences: [pocket_metadata_json]
  outputs:
    - name: poses
      type: docking_pose@1
      cardinality: many
      required: true
      provided_roles: [pose_file, metadata_json]
    - name: scores
      type: docking_score_table@1
      cardinality: one
      required: true
      provided_roles: [table_file, metadata_json]
resource_profile:
  tier: cpu-medium
executor:
  type: docker_image
```

`docking_pose@1` 和 `docking_score_table@1` 尚未在当前 registry 中落地，应作为新增标准 Artifact 的优先候选。

## 12. MD 模板

用途：对蛋白、复合物或候选分子进行分子动力学模拟。

```yaml
metadata:
  slug: md-simulation
parameters_schema:
  type: object
  properties:
    simulation_ns:
      type: number
      default: 10
    forcefield:
      type: string
      enum: [amber, charmm, opls]
artifacts:
  inputs:
    - name: complex
      type: docking_pose@1
      required: true
      role_preferences: [pose_file]
  outputs:
    - name: trajectory
      type: md_trajectory@1
      cardinality: one
      required: true
      provided_roles: [trajectory_file, topology_file, metrics_json]
    - name: report
      type: run_report@1
      cardinality: one
      required: true
      provided_roles: [report_json, report_markdown]
resource_profile:
  tier: gpu-large
  gpu_required: true
  expected_minutes: 240
  timeout_minutes: 1440
executor:
  type: slurm_job
```

MD 属于重计算，不应平台内置运行。第一版可以通过 SSH Job 过渡，稳定后迁移到 Slurm 或 K8s。

## 13. 打分重排模板

用途：对分子生成、对接或 ADMET 结果进行统一打分和排序。

```yaml
metadata:
  slug: scoring-rerank
parameters_schema:
  type: object
  properties:
    score_weights:
      type: object
artifacts:
  inputs:
    - name: molecules
      type: molecule_table@1
      required: true
      role_preferences: [table_file]
    - name: docking_scores
      type: docking_score_table@1
      required: false
      role_preferences: [table_file]
  outputs:
    - name: ranked_molecules
      type: molecule_table@1
      cardinality: one
      required: true
      provided_roles: [table_file, metadata_json]
resource_profile:
  tier: cpu-small
executor:
  type: builtin
```

## 14. 工具接入检查清单

新工具接入必须完成：

1. 选择最接近的工具模板。
2. 填写 Tool Contract v2 或可转换的 Tool Package / Remote API manifest。
3. 声明 `artifacts.inputs` 和 `artifacts.outputs`。
4. 声明 `resource_profile` 和 `executor.type`。
5. 提供 smoke example，包括参数和样例 Artifact 或样例文件。
6. 管理员设置可维护标签，不在前端硬编码筛选条件。
7. 通过契约校验、样例运行和结果 Artifact 校验。
8. 进入工具库、工作流节点库和智能体工具摘要。

## 15. 禁止事项

- 禁止为每个新工具新增工作流专属适配代码。
- 禁止在工具参数里放 `project_id`、用户 ID、真实文件路径或服务器凭据。
- 禁止把执行方式当成工具语义分类。
- 禁止下游工具偷偷改写上游 Artifact；应产出新的 ArtifactVersion。
- 禁止把可视化逻辑写进工具注册表。
