# 补齐 P-15~P-28 十一页 + mock 模型包（契约先行）

## Goal

按 `docs/06` §3 的 40 页清单，把剩下的 11 页做出来：P-15 分子生成、P-16 多肽设计、P-17 生成结果、P-21 性质预测提交、P-22 预测结果、P-23 虚拟筛选配置、P-24 筛选结果、P-25 对接结果详情、P-26 MD 提交、P-27 MD 结果、P-28 自由能结果。

这 11 页此前全部卡在 G-1（9 个模型资产未交付）。本计划用 **mock 模型包** 解耦：模型以符合 `aidd.sciminer/tool-package.v2` 的包交付，mock 版与真实版**同构**，真模型到位后只换镜像 tag 与 manifest，页面与平台零改动。

## Architecture（关键决定，不可改）

1. **工具就是模型**。中国医药 21 份文档里没有「内置工具」这个角色（`grep -rn "内置工具" docs/*.md` → 零命中）。`backend/app/tools/builtin_tools.py` 的 7 个进程内工具是上游 CPUmodel_V2 遗留，**本计划不往里加任何东西**，也不删（另立项）。
2. mock 以 **Tool Package** 交付，目录与 `example/MolP-PC/tool-package-v2/` 同构：`tool.yaml` + `schemas/` + `runner/` + `variants/` + `examples/` + `docs/`。
3. 执行方式两档：
   - `mock-local` 变体走 **`python_script` 执行器**（`backend/app/tasks/executors/python_script.py` 已存在），本机零镜像依赖，用于开发与演示；
   - `haiguang-dcu` 变体走 **`docker_image`**，镜像名先占位，真模型到位后替换。
4. **mock 必须在数据里可识别**：mock 包 `metadata.mock: true`；平台在建任务时把它写进 `task.extra_data["mock"] = True`；`GET /tasks/{id}`、`GET /results/{id}`、`GET /projects/{id}/results` 都返回 `mock` 布尔；产物 `manifest_json` 带 `"mock": true`。
5. **数值必须诚实**：能用 RDKit 真算的（MW / logP / TPSA / HBD / HBA / RotB / QED / SA / 分子式）真算；不能真算的（结合自由能、MD 轨迹、模型打分）写确定性合成值，并在 `report_json.mock_disclaimer` 里写明「演示数据，不可用于科研决策」。

## 冻结契约（六个 mock 模型包）

所有包 `metadata.version: 0.1.0`、`metadata.mock: true`、`exposure: {agent: true, workflow: true, direct_run: true}`、`runtime.executor_support: [docker_image, python_script]`。

### 1. `std-diff-molecule-generation` — P-15 提交、P-17 看结果
- 输入：`pocket`（`binding_pocket@1`，required）
- 输出：`molecules`（`molecule_table@1`，required）、`report`（`run_report@1`，optional）
- 参数：`num_molecules`（int，默认 100，1..1000）、`mw_min`/`mw_max`（number，默认 200/600）、`logp_min`/`logp_max`（默认 -1/5）、`seed`（int，默认 42）
- `molecule_table` 列：`smiles, inchi_key, mol_weight, logp, tpsa, hbd, hba, rotb, qed, sa_score, generation_score, rank`

### 2. `therapainter-peptide-design` — P-16 提交、P-17 看结果
- 输入：`pocket`（`binding_pocket@1`，required）
- 输出：`peptides`（`molecule_table@1`，required）、`report`（`run_report@1`，optional）
- 参数：`num_peptides`（默认 50，1..500）、`length_min`/`length_max`（默认 8/15）、`seed`
- `molecule_table` 列：`peptide_sequence, length, mol_weight, net_charge, isoelectric_point, hydrophobic_ratio, design_score, rank`

### 3. `admet-prediction` — P-21 提交、P-22 看结果
- 输入：`molecules`（`molecule_table@1`，required）
- 输出：`properties`（`molecule_table@1`，required）、`report`（`run_report@1`，optional）
- 参数：`task_groups`（array，enum 同 MolP-PC：Absorption/Distribution/Excretion/Metabolism/Toxicology/Tox21/Ecotoxicity/LD50，默认全选）
- `molecule_table` 列：`smiles, inchi_key, mol_weight, logp, tpsa, hbd, hba, rotb, qed, sa_score, admet_absorption, admet_distribution, admet_excretion, admet_metabolism, admet_toxicity, admet_tox21, admet_ecotoxicity, admet_ld50`

### 4. `vina-virtual-screening` — P-23 配置、P-24 列表、P-25 详情
- 输入：`receptor`（`protein_structure@1`，required）、`ligands`（`molecule_table@1`，required）、`pocket`（`binding_pocket@1`，optional）
- 输出：`ranked`（`molecule_table@1`，required）、`poses`（`ligand_structure@1`，required）、`report`（`run_report@1`，optional）
- 参数：`pharmacophore_min_features`（默认 3）、`docking_score_cutoff`（默认 -8.0）、`exhaustiveness`（默认 8，1..32）、`top_n`（默认 100，1..1000）、`seed`
- `ranked` 列：`smiles, inchi_key, mol_weight, logp, qed, stage_pharmacophore, stage_docking, stage_rescore, docking_score, rank, passes`
  - `stage_pharmacophore` / `stage_docking` / `stage_rescore` 为布尔，表示该分子通过/到达哪一层（漏斗用）
- `poses`（`ligand_structure@1`）：`structure_3d_sdf` 放 Top-N 姿势（多分子 SDF，每个分子 `_Name` 为 `pose-{rank}`），`metadata_json` 放
  `{"poses": [{"pose_id": "pose-1", "ligand_smiles": "...", "rank": 1, "docking_score": -9.4, "rmsd_lb": 0.0, "rmsd_ub": 0.0, "interactions": [{"residue": "MET769", "chain": "A", "type": "hydrogen_bond", "distance": 2.9}]}]}`

### 5. `gromacs-md-simulation` — P-26 提交、P-27 看结果
- 输入：`complex`（`protein_structure@1`，required；接受 prepared PDB）
- 输出：`trajectory`（`md_trajectory@1`，**新增标准**，required）、`report`（`run_report@1`，optional）
- 参数：`force_field`（enum `amber99sb-ildn`/`charmm36`，默认前者）、`duration_ns`（默认 100，0.1..1000）、`temperature_k`（默认 300）、`pressure_bar`（默认 1.0）、`seed`
- 新增标准 `backend/app/artifact_standards/schemas/md_trajectory.v1.yaml`：`type: md_trajectory`、`version: 1`，file roles
  - `topology_pdb` required, primary, allowed_formats `[pdb]`
  - `trajectory_dcd` required, allowed_formats `[dcd]`
  - `analysis_csv` required, allowed_formats `[csv]`（列：`time_ps, rmsd_nm, rmsf_nm, rg_nm, temperature_k, potential_kj_mol`）
  - `metadata_json` required, allowed_formats `[json]`

### 6. `gmx-mmpbsa-free-energy` — P-28 看结果
- 输入：`trajectory`（`md_trajectory@1`，required）
- 输出：`energies`（`molecule_table@1`，required）、`report`（`run_report@1`，required）
- 参数：`method`（enum `mmpbsa`/`mmgbsa`，默认 `mmgbsa`）、`frames`（默认 100）
- `energies` 列：`frame, delta_g_total, delta_g_vdw, delta_g_electrostatic, delta_g_polar_solvation, delta_g_nonpolar_solvation, delta_g_sasa`

## 前端 API 契约

页面**只消费既有接口**，不新增后端 REST 端点：

| 用途 | 接口 |
|---|---|
| 提交任务 | `POST /api/v1/tasks`（`{name, project_id, tool_id, tool_version_id, params, standard_input_uploads}`） |
| 取候选工具 | `GET /api/v1/tools?category=...&page_size=100`（按 slug 匹配） |
| 任务状态/进度 | `GET /api/v1/tasks/{id}`、`GET /api/v1/tasks/{id}/events`（SSE） |
| 结果详情 | `GET /api/v1/results/{task_id}` → `outputs[]`（含 `semantic_type`/`standard_type`/`role`）、`output_data`、`mock` |
| 产物下载 | `GET /api/v1/artifacts/{artifact_id}/versions/{version_id}/files/{role}/download` |
| 候选集回写 | `POST /api/v1/candidate-sets/{set_id}/items`、`POST /api/v1/projects/{id}/candidate-sets` |

**mock 标记的读取**：`GET /results/{task_id}` 与 `GET /tasks/{id}` 返回 `mock: boolean`。

## Global Constraints

- 不得修改 `backend/app/tools/builtin_tools.py`、`backend/app/tools/capabilities.py` 的既有条目（只允许追加 mock 包对应的 capability）。
- 不得新增 REST 端点；mock 标记走既有响应字段。
- 不得伪造「真实模型已验证」的表述：所有 mock 产物 `report_json.mock_disclaimer` 必填，UI 必显横幅。
- 迁移号占位：后端 agent 独占 `20261029_01`，不与其它分支冲突。
- 每个前端 agent 只改自己分配的 router / i18n 锚点，禁止改 `frontend/src/components/common/MockDataBanner.vue`（由 UI-1 创建）。

## PR 切分与文件所有权

| PR | 分支 | 内容 | 独占文件 |
|---|---|---|---|
| A | `feat/mock-model-packages` | 6 个 mock 包 + 1 个新标准 + 迁移 + mock 标记链路 + 测试 | `example/mock-models/**`、`backend/app/artifact_standards/schemas/md_trajectory.v1.yaml`、`backend/alembic/versions/20261029_01_*.py`、`backend/app/tools/capabilities.py`（仅追加）、`backend/app/api/v1/results.py`（仅加 mock 字段）、`backend/app/tasks/service.py`（仅加 mock 标记） |
| B | `feat/design-pages` | P-15/16/17 + `MockDataBanner.vue` + `api/design.ts` | `frontend/src/views/design/**`、`frontend/src/api/design.ts`、`frontend/src/types/design.ts`、`frontend/src/components/common/MockDataBanner.vue` |
| C | `feat/predict-screen-pages` | P-21/22/23/24/25 + `api/predict.ts` + `api/screening.ts` | `frontend/src/views/predict/**`、`frontend/src/views/screening/**` |
| D | `feat/md-pages` | P-26/27/28 + `api/md.ts` | `frontend/src/views/md/**` |

router / i18n 插入锚点：B 在 `WorkflowRunDetail` 后插 `/design/molecules`、`/design/peptides`、`/tasks/:id/results`；C 在 B 的三个之后插 `/predict`、`/tasks/:id/predictions`、`/screen`、`/tasks/:id/screening`、`/docking-results/:id`；D 在 C 之后插 `/md`、`/tasks/:id/md`、`/tasks/:id/free-energy`。i18n 各用独立命名空间（`design.*`/`predict.*`/`screening.*`/`md.*`），插在 `tasks` 命名空间之前。

## Review Focus

1. mock 标记是否真的贯穿「提交 → 任务 → 结果 → 页面横幅」四段，任一环断了都算不合格。
2. 产物是否真的符合 standard 的 file roles（`molecule_table@1` 必须有 `table_file` + `metadata_json`；`ligand_structure@1` 的主文件是 `structure_file`）。
3. 前端是否只消费既有接口、没有新造端点。
4. 漏斗（P-23/P-24）的阈值是否真的驱动过滤，而不是页面自己伪造掉队数字。
5. 页面是否在空态/错误态/加载态都有正确表现（不是只有 happy path）。
6. 是否出现「把 mock 数值当结论」的文案（例如「最佳亲和力 -9.4 kcal/mol」而不加演示标记）。
