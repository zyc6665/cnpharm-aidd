# K8s GPU 模型接入与镜像构建手册

| | |
|---|---|
| 文档编号 | DRP-MODEL-ONBOARD-K8S-v1.0 |
| 文档版本 | **v1.1**（2026-10-31，新增 AutoDock Vina CPU 对接模型；修复输入选择：manifest 中同名 `metadata_json` 条目会覆盖真实结构文件，`pick_input` 现按后缀校验并跳过元数据条目） |
| 上游 | `07-模型交付与运行规范.md`、`19-模型镜像构建与权重外置流程.md` |
| 适用范围 | 有 GPU 的 Kubernetes / k3s 集群；模型以容器镜像交付，由平台 `k8s_job` 执行器调度 |

---

## 1. 总体架构

```
平台 API (POST /api/v1/tasks)
  └─ 任务队列 / worker
       └─ k8s_job 执行器
            ├─ 解析 ToolPackage v2 清单（inputs / outputs / runtime）
            ├─ 物化输入：标准 Artifact 从对象存储拉到 PVC / 或直接上传
            ├─ 渲染 K8s Job（镜像 + GPU 资源 + env + volume）
            ├─ Job Pod 内：platform_run_v2.sh
            │    ├─ object_storage.py prepare   （拉输入）
            │    ├─ request_to_legacy.py        （可选：旧请求桥接）
            │    ├─ 模型入口 platform_run.sh
            │    ├─ postprocess_result.py       （可选：legacy → result.v2）
            │    └─ object_storage.py validate  （校验 result + 产物不越界）
            └─ 收集 output/ → 写 Artifact / DataFile → 页面可见
```

关键点：**平台只认标准契约**（`aidd.sciminer/result` + 标准 Artifact 类型），
模型自己的输入/输出格式差异全部由镜像适配层消化，不改平台代码。

## 2. 前置条件

1. k3s/k8s 可达，且节点有 GPU；确认 `kubectl get nodes`、`nvidia.com/gpu` 资源。
2. 内网 registry（本项目 `10.202.2.228:30500`，k3s 内置 registry NodePort 30500）。
3. 对象存储（MinIO）可达；平台侧 `K8S_ADAPTER_OBJECT_STORAGE_*` 配置正确。
4. 模型代码与权重在构建机上可读；conda 环境可 `conda-pack`。
5. 平台 DB 已迁移到最新 head，`EXECUTOR_ENABLED_K8S=true`。

## 3. 镜像构建（以 MolP-PC 为例）

```bash
# 3.1 在模型所在容器/机器打包 conda 环境
conda-pack -n molp-pc -o /workspace/k8s-model-build/molp/env.tar.gz
cp -r /workspace/MolP-PC /workspace/k8s-model-build/molp/MolP-PC
# 模型权重按目录一并拷入；本批三模型权重随镜像分发

# 3.2 准备 build context（Dockerfile + env.tar.gz + model.tar.gz + platform_adaptor）
#     Dockerfile 模板见 deploy/model-images/k8s/molp-pc/Dockerfile

# 3.3 构建并推送
docker build --network host -t 127.0.0.1:30500/aidd/compute-molp-pc:1.0.0 .
docker push 127.0.0.1:30500/aidd/compute-molp-pc:1.0.0
# 记录输出中的 digest（sha256:...），迁移里用 digest 而不是 tag 引用
```

三模型最终镜像 digest：

| 模型 | 镜像 | digest（sha256） |
|---|---|---|
| MolP-PC | `aidd/compute-molp-pc:1.0.0` | `e72ee34c4ea8850dcc715dcd43fc0d16c92e3a2643524e1ccac7008551800cc9` |
| MSIGN | `aidd/compute-msign:1.0.0` | `babc088f46692bf5b4c433bf3a34cb5ea40587351273e449cabf55c91512bca8` |
| Pocket2Mol | `aidd/compute-pocket2mol:1.0.0` | `f834fd01c614c531d861d55a32b2b60454575b12a3a04f861dc69d859a72dd26` |
| AutoDock Vina（CPU） | `aidd/compute-vina:1.0.0` | `0788db8da9d7b84423cebe5986fceb898b89a0b58b97bd5c10386abfd6c0e50b` |
| TheraPainter | `aidd/compute-therapainter:1.0.0` | `61d2d40853cc9153c73bbf42d4a16b76fd9966dd38f3b4194f0db7c7cd7f8a2c` |
| GROMACS MD | `aidd/compute-gromacs:1.0.0` | `28f64b63cd573e41684d794aa6f34c615f16e9b340303e9c04eac5e6391cab95` |
| gmx_MMPBSA | `aidd/compute-gmx-mmpbsa:1.0.0` | `d61753513a21ae4909f44611f3f7cc568b1db589f9d8238107928532919e94fb` |

## 4. 注册平台工具

在 `backend/alembic/versions/` 增加一个迁移（参照 `20261031_09_model_packages.py`、
更早的 `20261030_01_lvpocket_model_package.py`）：

* `tools` 行：`category=model`、`provider=platform`、`config.type=k8s_job`；
* `tool_versions` 行：`config` 写 `runtime.artifacts.inputs/outputs`、
  `runtime.launcher.primary.image`（用 digest）、GPU 资源、`timeout_sec`；
* 清单必须通过 `tool_package_manifest` 校验：输入 `type` 用受控标准类型
  （`molecule_table@1` / `protein_structure@1` / `ligand_structure@1` 等），
  输出同理；`role_preferences` 对应标准 schema 的文件角色。

迁移后：`alembic upgrade head`，并核对 `alembic heads` 单头。

## 5. 平台配置

`backend/.env`（生产用密钥管理，不落库）：

```
EXECUTOR_ENABLED_K8S=true
K8S_ADAPTER_KUBECONFIG=<kubeconfig 路径或 in-cluster>
K8S_ADAPTER_NAMESPACE=sciminer-model-jobs
K8S_ADAPTER_OBJECT_STORAGE_ENDPOINT=http://<minio-cluster-ip>:9000   # 必须集群内地址，不能用 NodePort
K8S_ADAPTER_OBJECT_STORAGE_ACCESS_KEY=...
K8S_ADAPTER_OBJECT_STORAGE_SECRET_KEY=...
K8S_ADAPTER_OBJECT_STORAGE_BUCKET=...
```

> 常见坑：把 `..._ENDPOINT` 配成 `http://10.202.2.228:30900` 会让 Pod 内 minio SDK
> 收到「S3 API Requests must be made to API port」的非 XML 响应；要用 Service 的
> `9000` 端口（集群内 DNS/ClusterIP）。

## 6. E2E 验证

```bash
python scripts/e2e_model_task.py \
  --tool <tool_id> --version <version_id> \
  --standard-file smiles_csv=./samples.csv --project <project_id> \
  --name "K8s E2E MolP" --timeout 1800
```

成功标志：`POLL success 100.0`；任务 `status=SUCCESS`；`artifacts` 中类型为标准类型；
`artifacts` 表三列身份一致。

本批实测：

| 任务 | 结果 | 产物 |
|---|---|---|
| K8s E2E MolP 11 | SUCCESS | `molecule_table@1` + `run_report@1` |
| K8s E2E MSIGN 2 | SUCCESS | `molecule_table@1` |
| K8s E2E Pocket2Mol | SUCCESS（581.7s） | `molecule_table@1` + `ligand_structure@1` + `run_report@1` |
| K8s E2E MSIGN batch SDF | SUCCESS（28.0s） | `molecule_table@1`（2 条） + `run_report@1` |
| K8s E2E MSIGN SMILES v4 | SUCCESS | `molecule_table@1`（3 成功 + 1 解析失败行） + `run_report@1` |
| K8s E2E Vina 11 | SUCCESS | `molecule_table@1`（3 配体，best -5.871 kcal/mol） + `ligand_structure@1` + `run_report@1` |

### 6.1 MSIGN 批量与 SMILES 输入

MSIGN 支持两种批量入口（迁移 `20261031_10` / `20261031_11`，工具版本 1.2.0）：

* `ligand_sdf`（`ligand_structure@1`，多记录 SDF）：每个记录是一个配体，逐条预测，
  输出一行一分子；适合已有 3D 构象/对接位姿的场景。
* `ligand_smiles`（`molecule_table@1` CSV，含 SMILES 列）：镜像内 `smiles_to_sdf.py`
  用 RDKit ETKDG 批量生成 3D 构象后再预测；解析/嵌入失败的分子写成 `error` 行，
  报告里给出 `smiles_conversion.requested/written/failed`。

两者都输出 `molecule_table@1`（`table_file=artifacts/affinity.csv` +
`metadata_json`）与 `run_report@1`，逐分子列含 `prediction.predicted_affinity`、
`prediction.predicted_ligand_to_pocket` 等。

> 构建 MSIGN 镜像前，先在构建目录执行
> `bash deploy/model-images/k8s/msign/prepare_build_context.sh`，由 `model.tar.gz`
> 生成带 `--center-from-protein` 补丁的 `model_v2.tar.gz`（Dockerfile 使用后者）。

> **重要限制**：SMILES-only 路径没有真实对接，配体只是用 ETKDG 生成构象并放在
> 「离蛋白几何中心最近的蛋白重原子」处（medoid 锚点），仅用于打通“一批 SMILES 快速
> 出分”的流程，亲和力数值不具备结合模式意义。需要可靠分数时，请提供已对接的
> `ligand_sdf`（真实位姿）。镜像构建时必须让 MSIGN 的 `platform_run.sh` 调
> `smiles_to_sdf.py` 时带 `--center-from-protein "${PROTEIN_PDB}"`，否则配体停在原点，
> 会报 `No protein pocket atoms were found within 5 Angstrom of the ligand`。

## 7. 踩坑清单

1. **conda-pack 的 PATH**：`conda-unpack` 前必须 `PATH=/opt/conda/bin:$PATH`，否则
   激活脚本找不到 `conda-unpack`；entrypoint 也要显式用 `/opt/conda/bin/python`。
2. **minio 依赖**：镜像内 `python3` 是系统解释器时，务必把 `minio==7.2.10` 装进
   conda 环境（`pip install -i https://pypi.org/simple minio==7.2.10`），否则适配层
   `object_storage.py` 在 Pod 内 ImportError。
3. **build context 路径**：容器里只能看到 `/workspace`（映射宿主 `/data/zhouyc/kaiwu`）；
   在宿主其它目录打包的 `env.tar.gz` 要 `docker cp` 拷到 build context，否则
   `COPY` 报 `gzip: unexpected end of file`。
4. **Registry 地址**：k3s 内置 registry 在每节点 `127.0.0.1:30500`；镜像引用统一写
   `10.202.2.228:30500/...`，Job 由节点拉取。
5. **旧 runner 参数**：部分模型不认 `--model-root`，适配层已用 `MODEL_ROOT_ARGS`
   探测后再传；否则 `Unknown argument` 退出码 2。
6. **输入字段**：MolP CSV 表头必须是 `SMILES`（大写）；Pocket2Mol 需要 `protein_pdb`
   标准输入；MSIGN 需要 `protein_pdb` + 三选一的配体输入（`ligand_pdb` /
   `ligand_sdf` 多记录 SDF / `ligand_smiles` CSV 表）。
7. **GPU 设备字符串**：模型内部若写死 `device='cuda'`，在无 GPU 环境会崩；适配层已
   对 `device=="auto"` 做回落（`cpu`）。

## 8. 迁移到 DCU

只改镜像底座与模型 runner 的 device 适配，`inputs`/`outputs`/`runtime.weights` 契约
不变：把 `compute-*` 镜像改成 DCU 基础镜像（ROCm/DTK），保持 `platform_run_v2.sh`
入口和标准 result.v2 输出即可。DCU 真机验证仍为 `D-34` 阻塞项。

## 9. 相关文档

- `19-模型镜像构建与权重外置流程.md`（镜像分层、权重外置）
- `07-模型交付与运行规范.md`（10 模型清单与运行契约）
- `23-模型接入操作手册（SSH直连与工具注册）.md`（已弃用的 SSH 历史方案）

## 10. 当前已接入的 K8s 模型清单（2026-10-31）

| 工具 slug | 镜像 | 调度 | 输入 | 输出 |
| --- | --- | --- | --- | --- |
| `molp-pc-property-prediction` | `aidd/compute-molp-pc@sha256:e72ee34c…` | GPU | `smiles_csv`（表头 `SMILES`） | `molecule_table@1` + `run_report@1` |
| `msign-affinity-prediction` | `aidd/compute-msign@sha256:babc088f…` | GPU | `protein_pdb` + 三选一：`ligand_pdb` / `ligand_sdf`（多记录）/ `ligand_smiles`（CSV 表） | `molecule_table@1` + `run_report@1` |
| `pocket2mol-pocket-ligand-generation` | `aidd/compute-pocket2mol@sha256:f834fd01…` | GPU | `protein_pdb` + `pocket` 参数 | `molecule_table@1` + `ligand_structure@1` + `run_report@1` |
| `autodock-vina-docking` | `aidd/compute-vina@sha256:0788db8d…` | CPU | `protein_pdb` + `ligand_sdf`（SDF 可多配体） | `molecule_table@1` + `ligand_structure@1` + `run_report@1` |
| `boltz2-structure-prediction` | `aidd/compute-boltz2@sha256:83dc125a…` | GPU | 蛋白序列（`parameters.sequence`） | `protein_structure@1`（`structure.pdb` + `metadata.json`） |
| `boltz2-affinity-prediction` | `aidd/compute-boltz2-affinity@sha256:d380abc4…` | GPU | 蛋白序列（`parameters.sequence`）+ `ligand_smiles`（CSV，按行逐配体推理） | `molecule_table@1`（亲和力/概率/置信度/iptm）+ `run_report@1` |
| `therapainter-peptide-prediction` | `aidd/compute-therapainter@sha256:61d2d408…` | GPU（CPU 可降级） | `parameters.sequence`（多肽序列，多行/FASTA，可批量） | `molecule_table@1`（活性/MIC/毒性）+ `run_report@1` |

Boltz-2 权重以 hostPath 只读挂载：宿主
`/data/zhouyc/k8s-model-build/boltz2_cache` → 容器 `/opt/boltz2_cache`（conf / aff /
mols 三件，约 6.2 GB），因此需要能调度到该宿主的 nodeSelector；
`runtime.weights.mounts` 已写在迁移 `20261031_13` 的工具配置里。

Boltz-2 纯离线单序列：镜像内生成 `>query\n<SEQ>` 的 A3M 文件并在 YAML 里
`msa: <path>` 引用（`msa: empty` 会被 Boltz-2 判为非法）。镜像未装
cuequivariance，入口固定加 `--no_kernels`。
