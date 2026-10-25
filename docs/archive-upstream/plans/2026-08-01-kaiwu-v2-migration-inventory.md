# Kaiwu 模型工具 v2 契约迁移盘点

## 范围

盘点对象是当前平台 SQLite 数据库中已发布且 `ToolVersion.config.type=ssh_job` 的模型工具，
以及 `10.202.2.228` 机器 `kaiwu` 容器中可见的相关模型目录。盘点方式为只读：

- 本地读取 `backend/storage/scitool.db` 中当前工具和版本配置。
- 本地读取 `example/**/platform_tool*.json` 中的历史 SSH 配置。
- 远端只执行 `ssh zhouyc@10.202.2.228` 和 `docker exec kaiwu` 的 `ls`、`find`、
  `stat`、`sha256sum`、`grep`、`nvidia-smi` 等只读命令。

本次未修改远端文件、数据库记录或已发布工具。

## 远端运行环境事实

| 项目 | 盘点结果 |
| --- | --- |
| 宿主机 | `10.202.2.228`，hostname 为 `4090` |
| 容器 | `kaiwu`，运行中 |
| 容器 image ID | `sha256:84ddbbadf9fe3fa2a45f6a4695853eb471097fd0ea66d42affa0fb217dc5c608` |
| 挂载 | `/data/zhouyc/kaiwu => /workspace` |
| GPU | 8 x NVIDIA GeForce RTX 4090，driver `550.135`，每卡约 `24564 MiB` |
| 容器默认 Python | `python` 不存在，各模型依赖自己的 conda/env Python |
| 平台任务目录 | `/workspace/platform-jobs`，已有多条旧 `result.json` 输出 |

结论：当前部署是“单容器多模型 + 多个私有 conda/env 路径”。v2 迁移时不能把这些路径当成
平台契约，只能作为构建 Runtime Env 产物的输入证据。

## 当前 DB 已发布 ssh_job 工具

| slug | version | 远端入口 | 旧输入 | 近期输出证据 | v2 目标 |
| --- | --- | --- | --- | --- | --- |
| `lvpocket-pocket-prediction` | `0.1.2` | `/workspace/LVpocket-2/platform_run.sh` | `protein_pdb` | 旧结果含 `pocket0.pdb`、`pocket0.mol2`、`protein_pocket_residues.pdb`、PSIPRED 文件 | `protein_structure@1 -> binding_pocket@1 + run_report@1` |
| `molp-pc-property-prediction` | `0.1.1` | `/workspace/MolP-PC/platform_run.sh` | `smiles_csv` | 旧结果含 `artifacts/cb_data_result.csv` | `molecule_table@1 -> molecule_table@1 + run_report@1` |
| `msign-affinity-prediction` | `0.1.1` | `/workspace/MSIGN/platform_run.sh` | `protein_pdb`、`ligand_pdb` | 旧结果含 `prediction.json`、预处理 PDB、DGL/RDKit 中间文件 | `protein_structure@1 + ligand_structure@1 -> molecule_table@1 + run_report@1` |
| `gcdm-pocket-generation` | `0.1.2` | `/workspace/GCDM-2model_claude/platform_run.sh` | 旧配置为 `task_id/params/input_files`，实际需要 `pocket_pdb` | 样例含 `generated_molecules.sdf` | `binding_pocket@1 -> molecule_table@1 + ligand_structure@1[]` |
| `janus-qubo-ga-generation` | `0.1.0` | `/workspace/Janus-QUBO/platform_run.sh` | 参数驱动，`qubo_csv/ising_csv` 可选 | 旧结果含 `generated_smiles.csv`、latent HDF5 | 需要决定“参数型工具/优化问题”标准；候选输出 `molecule_table@1 + run_report@1` |
| `flowpepdock-docking` | `0.1.2` | `/workspace/FlowPepDock_handover_20260507/platform_run.sh` | `receptor_pdb`、`peptide_pdb` | 未找到近期样例 result；脚本输出 peptide docking 结果 | 需要新增肽/蛋白-肽复合物标准 |
| `mmcd-peptide-generation` | `0.1.0` | `/workspace/MMCD/MMCD_0/platform_run.sh` | 参数驱动，`fasta` 可选 | 未找到近期样例 result；脚本支持序列和结构生成 | 需要新增肽序列/肽结构标准 |
| `dualpep-peptide-prediction` | `0.1.0` | `/workspace/TheraPainter/platform_run.sh` | `sequences` 或 `sequences_file` | 旧结果含 `predictions.csv`、`predictions.json` | 需要新增肽序列表/肽属性表标准 |
| `therapainter-peptide-evolve` | `0.1.0` | `/workspace/TheraPainter/platform_run.sh` | `sequences` 或 `sequences_file` | 与 DualPep 共用入口，通过 `THERAPAINTER_DEFAULT_TASK` 区分 | 需要新增肽序列表标准 |

## 远端存在但当前 DB 未发布的工具

| 工具 | 证据 | 建议 |
| --- | --- | --- |
| `pocket2mol-pocket-ligand-generation` | `example/pocket2mol/platform_tool.ssh_job.json` 指向 `/workspace/Pocket2Mol-main/platform_run.sh`；近期平台任务有成功 `Pocket2Mol sampling completed` | 纳入第二批，目标为 `binding_pocket@1 -> molecule_table@1 + ligand_structure@1[]` |
| `DrugCLIP` | 容器内存在 `/workspace/DrugCLIP/platform_run.sh` 和大权重 `checkpoint_best.pt`，但当前 DB 未发布 | 暂不迁移，先补工具登记和标准 Artifact 设计 |
| `LVpocket` 旧目录 | 容器内有 `/workspace/LVpocket`、`/workspace/LVpocket-2_for_cpupdb` | 暂不作为平台工具迁移源，避免重复入口 |

## Runtime Env 与权重盘点

| 工具 | Python/env | 权重/模型文件证据 | 迁移要求 |
| --- | --- | --- | --- |
| LVpocket | `/workspace/LVpocket-2/env/bin/python`，Python `3.10.20` | `new_best_1/*.hdf`，最大约 `1.5 GB` | 构建独立 LVpocket runtime image 或 conda-pack；权重 manifest 覆盖全部实际使用的 `.hdf` |
| MolP-PC | `/home/zhuwy/.conda/envs/molp-pc/bin/python`，Python `3.8.20` | `predict/model/*.pth`，约 `121-123 MB` 每组 | 已有模型侧规范包，下一步补真实 runtime/weights 摘要 |
| GCDM | `/home/zhuwy/.conda/envs/STD-Diff/bin/python`，Python `3.10.20` | `weights/gcdm_crossdocked_ca_cond_gcpnet_epoch376.ckpt`，约 `88 MB` | 用 `binding_pocket@1` adapter 包装输入，产出 SDF/table |
| FlowPepDock | 配置使用 `/home/zhuwy/.conda/envs/flowpepdock/bin/python` | `flowpepdock_best.pt`、SO3 `.npy`、PoseCred 权重 | 先定义肽/复合物 Artifact，再迁移 |
| MSIGN | 配置使用 `/home/zhuwy/.conda/envs/MSIGN/bin/python` | `full_finetune_model.pt`、`pretrain_general_model.pt` | 可优先迁移为亲和力表 + 报告 |
| Janus-QUBO | `/home/zhuwy/.conda/envs/janus-qubo/bin/python`，Python `3.10.20` | `recon_loss=0.0043.ckpt` | 需要平台决定参数型/优化问题工具如何表示输入 |
| MMCD | `/home/zhuwy/.conda/envs/MMCD/bin/python`，Python `3.9.12` | 多个 `ckpt/**/*.ckpt`，最大约 `291 MB` | 先定义肽生成标准 Artifact |
| TheraPainter | 配置使用 `/home/zhuwy/.conda/envs/TheraPainter/bin/python` | DualPep、activity/toxicity、RL evolve 权重 | 先定义肽序列/属性表标准 |
| Pocket2Mol | `/home/zhuwy/.conda/envs/Pocket2Mol-h100/bin/python`，Python `3.10.12` | `ckpt/pretrained_Pocket2Mol.pt`，约 `45 MB` | 第二批迁移，复用已建 v2 示例 |

所有 `runtime` 字段最终必须写入 Tool Package v2 manifest：

- `runtime.artifacts.primary.image_digest`
- `runtime.artifacts.fallback.sha256`
- `runtime.weights.manifest_sha256`
- `runtime.cache_policy.key_fields`

这些摘要不能用当前表中的示例占位值发布。示例占位只允许停留在模板或未发布草稿中。

## 标准 Artifact 缺口

当前平台 registry 已覆盖：

- `protein_structure@1`
- `binding_pocket@1`
- `molecule_table@1`
- `ligand_structure@1`
- `run_report@1`

迁移下面工具前需要新增或确认标准：

| 需求 | 涉及工具 | 建议标准 |
| --- | --- | --- |
| 肽序列输入/输出 | DualPep、TheraPainter、MMCD | `peptide_sequence_table@1` |
| 肽三维结构 | MMCD、FlowPepDock | `peptide_structure@1` |
| 蛋白-肽 docking/复合物 | FlowPepDock | `protein_peptide_complex@1` 或 `docking_pose@1` |
| 参数型生成/优化问题 | Janus-QUBO、MMCD seq-only | `optimization_problem@1`，或放宽 v2 允许无文件输入工具 |
| 亲和力/打分表 | MSIGN、DualPep | 可先使用 `molecule_table@1`/未来 `score_table@1` |

不要为了快速迁移把这些工具的私有字段重新塞回 `semantic_inputs` 或旧 `output_schema`。

## 分批迁移计划

### 第 1 批：现有标准可覆盖

1. `lvpocket-pocket-prediction`
   - 复用 `example/LVpocket/tool-package-v2`。
   - 远端 adapter 将旧 `pocket0.pdb` 和 `protein_pocket_residues.pdb` 收敛为：
     - `residue_pocket_pdb`
     - `atom_pocket_pdb`
     - `pocket_metadata_json`
   - 注意当前远端结果的 `distance_cutoff=8.0`，如果平台标准要固定 `10A`，需要明确重跑黄金样例。
2. `molp-pc-property-prediction`
   - 复用 `example/MolP-PC/tool-package-v2` 和 `model/MolP-PC`。
   - 旧 `cb_data_result.csv` 收敛为 `properties: molecule_table@1`。
3. `msign-affinity-prediction`
   - 新建 `example/MSIGN/tool-package-v2`。
   - 输入 `protein_structure@1 + ligand_structure@1`。
   - 输出 `molecule_table@1`，每行包含 ligand/complex ID、predicted affinity、模型名、距离阈值。
   - 原始预处理 PDB/DGL/RDKit 文件放入 `run_report@1` 或辅助调试包，不进主编排链路。

### 第 2 批：小分子生成链路

1. `gcdm-pocket-generation`
   - 新建 `example/GCDM/tool-package-v2`。
   - 输入改为 `binding_pocket@1`，adapter 从 `residue_pocket_pdb` 或 `atom_pocket_pdb` 生成旧 `pocket_pdb`。
   - 输出 `molecule_table@1 + ligand_structure@1[]`。
2. `Pocket2Mol`
   - 当前 DB 未发布，但容器和示例配置存在，建议纳入同一批。
   - 复用已有 `example/pocket2mol/tool-package-v2`，把旧 `protein_pdb + center` 入口改成消费 `binding_pocket@1`。

### 第 3 批：肽与 docking 标准扩展

1. 先新增标准 Artifact：
   - `peptide_sequence_table@1`
   - `peptide_structure@1`
   - `protein_peptide_complex@1` 或 `docking_pose@1`
2. 再迁移：
   - `dualpep-peptide-prediction`
   - `therapainter-peptide-evolve`
   - `mmcd-peptide-generation`
   - `flowpepdock-docking`

### 第 4 批：参数型/优化工具

`janus-qubo-ga-generation` 当前可以无文件输入，仅靠参数生成 SMILES。v2 validator 当前要求至少一个
标准输入，因此迁移前必须先做一个平台设计决策：

1. 允许 Tool Package v2 出现 parameter-only 工具；或
2. 新增 `optimization_problem@1`，把 QUBO/Ising/latent optimization 输入标准化。

在决策前，不建议强行迁移为伪 `molecule_table@1` 输入。

## 单工具迁移操作模板

每个工具按同一流程执行：

1. **冻结旧工具**
   - 不删除旧 `ToolVersion`。
   - 新 v2 先作为 draft/unvalidated Tool Package 存在。
2. **生成模型侧规范包**
   - 如模型代码较大，先只整理 wrapper、`MODEL_PACKAGE.yaml`、权重说明和 runtime 说明。
   - 不提交真实权重、conda env、wheelhouse 或远端私有路径。
3. **生成 Tool Package v2**
   - 从 `example/model-platformization-template` 或已有同类 v2 示例复制。
   - `tool.yaml` 只声明标准 Artifact、参数 schema、adapter、runtime 和 variants。
4. **加远端 adapter**
   - 保留旧入口或原始模型推理逻辑。
   - 新增薄 adapter：标准 request -> 旧输入布局 -> 旧模型 -> `result.v2`。
   - 不让平台新增模型私有字段。
5. **生成 Runtime Env 摘要**
   - 当前 `kaiwu` 容器 image ID 可作为盘点证据，不等同于最终 runtime digest。
   - 构建或打包每个模型自己的 runtime image/conda-pack 后，填入真实 digest/SHA。
6. **黄金样例验证**
   - 每个工具至少一条公开或可审计样例。
   - 保存输入哈希、输出 `result.v2`、产物哈希、GPU/驱动、权重 manifest、执行器类型。
7. **注册和灰度**
   - 导入 v2 package 为 draft。
   - 校验、签名、发布。
   - Agent/workflow 切换到 v2 后，观察任务中心和 ArtifactVersion 创建结果。

## 只读远端命令模板

```bash
SSHPASS="<from secret store>" sshpass -e ssh zhouyc@10.202.2.228 \
  'docker exec kaiwu bash -lc "find /workspace -maxdepth 3 -name platform_run.sh -type f"'
```

```bash
SSHPASS="<from secret store>" sshpass -e ssh zhouyc@10.202.2.228 \
  'docker exec kaiwu bash -lc "nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader"'
```

实际执行时必须从密钥管理或 `.env` 读取密码，不要把明文密码写入命令历史、文档或 Tool Package。

## 风险和阻塞项

- 当前 `kaiwu` 容器内默认 `python` 不存在，多个工具通过私有 conda 路径运行。迁移必须先固化
  Runtime Env 产物，否则 Slurm/K8s 无法复现。
- 当前 DB 尚无 `tool_packages` 已发布记录，旧工具仍在 `tools/tool_versions` 路径运行。
- `pocket2mol` 有远端和 example 配置，但不在当前 DB 已发布工具列表中，迁移时需要确认是否重新登记。
- 肽和 docking 工具不能在没有标准 Artifact 的情况下进入 v2 主路径。
- Janus-QUBO 暴露了 v2 对 parameter-only 工具的设计缺口，需要先决策再迁移。

## 下一步执行建议

1. 为第 1 批建立三个 v2 包：
   - `example/LVpocket/tool-package-v2` 真实化 runtime/weights 摘要。
   - `example/MolP-PC/tool-package-v2` 对齐当前 DB 版本 `0.1.1`。
   - 新建 `example/MSIGN/tool-package-v2`。
2. 给第 1 批每个工具写包内 adapter 测试和黄金 result.v2 样例。
3. 远端只新增 v2 wrapper 文件，不覆盖旧 `platform_run.sh`。
4. 跑真实黄金样例后，再通过 Tool Package API 导入 draft，签名发布。
