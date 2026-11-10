# 模型接入教程：镜像构建 + Tool Package v2 + 发布（k8s 调度）

> 面向管理员/算法同学。按本教程可把一个模型从“本地代码/权重”做成平台可调度的模型，并在「工具管理 → 新建模型」上架。
> 平台当前执行方式：**k8s_job**（GPU 通过 `nvidia.com/gpu` 申请），集群 `k3s-4090`，仓库 `10.202.2.228:30500`，模型作业命名空间 `sciminer-model-jobs`。

---

## 1. 构建模型镜像

### 1.1 基础要求
- 基于与集群驱动匹配的 CUDA 基座（示例 `nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04`；与 `docs/08A` 记录一致）。
- 只装**运行期**依赖，不要把训练代码/数据集打进镜像。
- 单个模型镜像必须自包含：入口脚本、模型推理代码、必要 Python 依赖。
- **权重外置**：不要把权重打进镜像；用 `runtime.weights.mounts` 把宿主机/共享存储只读挂到容器 `/opt/model/weights`。
- 容器内**只写 `/work/out`**；不要写宿主机绝对路径、不要引用宿主机目录。

### 1.2 Dockerfile 示例
```dockerfile
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip && rm -rf /var/lib/apt/lists/*
RUN pip3 install --no-cache-dir torch==2.4.0 rdkit numpy
COPY entrypoint.sh /opt/model/entrypoint.sh
RUN chmod +x /opt/model/entrypoint.sh
WORKDIR /work
ENTRYPOINT ["/opt/model/entrypoint.sh"]
```

### 1.3 入口契约（必须遵守）
平台以 K8s Job 启动镜像，模型需：
- 读环境变量 `DRP_TASK_FILE`（`/work/task.json`）拿任务与参数；
- 输入已由平台下载到 `DRP_IN_DIR`（`/work/in/<role>/`）；
- 写 `DRP_RESULT_FILE`（`/work/result.json`，**不是 output.json**）；
- 周期性写 `DRP_PROGRESS_FILE`（`/work/out/progress.json`，`{"pct":35,"stage":"..."}`）；
- 退出码：`0` 成功；`10` 输入非法；`11` 权重缺失；`12` 显存不足；`13` 超时；`1` 其他。
- `result.json` 必填：`status`、`metrics` 或 `artifacts` 至少一个、`timing`；所有 `artifacts[].path` 必须落在 `/work/out` 内。
- GPU：从 `DRP_DEVICE`（默认 `cuda:0`）取设备，不要硬编码；容器内逻辑序号恒为 0。

### 1.4 推送镜像
```bash
docker build -t 10.202.2.228:30500/aidd/compute-<slug>:<version>-cu121 .
docker push 10.202.2.228:30500/aidd/compute-<slug>:<version>-cu121
# 取 digest（发布时建议填 digest，保证不可变）
docker inspect --format='{{index .RepoDigests 0}}' 10.202.2.228:30500/aidd/compute-<slug>:<version>-cu121
```

---

## 2. 编写 Tool Package v2（`aidd.sciminer/tool-package`）

> 平台以该 manifest 作为工具/模型契约：输入输出用**标准 Artifact 类型**，运行参数用 `parameters_schema`，资源画像与镜像在 `runtime`。

### 2.1 完整示例（以口袋条件分子生成为例）
```yaml
api_version: aidd.sciminer/tool-package
kind: ToolPackage
metadata:
  slug: pocket2mol-pocket-ligand-generation
  name: Pocket2Mol 口袋分子生成
  version: 1.0.0
  description: 基于 Pocket2Mol 的口袋条件分子生成
artifacts:
  inputs:
    - name: protein_pdb
      title: 蛋白结构
      type: protein_structure@1
      required: true
      role_preferences: [prepared_pdb, structure_file]
  outputs:
    - name: molecules
      type: molecule_table@1
      cardinality: one
      required: true
    - name: ligands
      type: ligand_structure@1
      cardinality: one
      required: true
    - name: report
      type: run_report@1
      cardinality: one
      required: false
parameters_schema:
  type: object
  properties:
    device: { type: string, enum: [auto, gpu, cpu], default: auto }
    num_samples: { type: integer, minimum: 1, maximum: 1000, default: 100 }
    center_x: { type: number }
    center_y: { type: number }
    center_z: { type: number }
    pocket_radius: { type: number, default: 10.0 }
  additionalProperties: false
runtime:
  python: "3.8"
  cuda: "11.3"
  executor_support: [k8s_job]
  weights:
    mounts:
      - name: weights
        host_path: /var/drp/model-cache/pocket2mol/1.0.0
        mount_path: /opt/model/weights
        read_only: true
  artifacts:
    primary:
      kind: container
      image: 10.202.2.228:30500/aidd/compute-pocket2mol@sha256:<digest>
      image_digest: sha256:<digest>
      includes: [python, torch, rdkit]
variants:
  - name: nvidia-cuda
    accelerator: nvidia_cuda
    executor_types: [container]
    image: 10.202.2.228:30500/aidd/compute-pocket2mol@sha256:<digest>
```

### 2.2 标准 Artifact 类型（节选）
| 用途 | type | 说明 |
|---|---|---|
| 蛋白结构 | `protein_structure@1` | PDB/mmCIF |
| 结合口袋 | `binding_pocket@1` | 口袋定义（中心/体积/残基） |
| 分子表 | `molecule_table@1` | CSV/SDF 候选表 |
| 配体结构 | `ligand_structure@1` | SDF/MOL2 |
| 运行报告 | `run_report@1` | 报告/说明 |
| 亲和力/ADMET | `molecule_table@1` / 专用 semantic | 按结果列声明 |

> 输入/输出必须用平台已支持的标准类型；未知类型会在发布校验被拒。

### 2.3 参数 schema
- `parameters_schema` 用 JSON Schema（`type/properties/required/enum/min/max/default/addditionalProperties:false`）。
- 管理员在「运行参数」步骤可用表单编辑，高级用户切 JSON。

### 2.4 资源画像与 GPU
- `runtime.artifacts.primary.image` 建议填 **digest**（不可变）。
- GPU 需求由工具版本的资源画像（`resource_profile`：`tier/cpu/memory_gb/gpu_required/gpu_memory_gb/timeout_minutes/parallelism`）表达，K8s 会以 `nvidia.com/gpu` 申请；**4090 单卡 24GB，显存需求超 24G 的模型会被准入拒绝（预期行为）**。
- 权重挂载 `runtime.weights.mounts`：`host_path` 必须绝对路径，容器内只读挂载。

---

## 3. 在平台发布（工具管理 → 新建模型）

1. 进入「管理后台 → 工具与模型 → 工具管理 → 新建模型」；
2. ① 基本信息：名称、slug、能力族（model_family）、分类、标签、简介；
3. ② 镜像与运行：填镜像（digest）、启动命令、环境变量、资源画像（CPU/内存/GPU/显存）、超时；
4. ③ 输入/输出契约：按 §2 填 artifacts（标准类型/必填/role_preferences）；
5. ④ 运行参数：填 `parameters_schema`；
6. ⑤ 版本与发布：版本号、变更说明 → **校验/冒烟** → 发布。

> 工具类型固定 `k8s_job`，页面不再提供 Docker/Python/SSH 选择，也不再需要旧版 Agent 语义映射。

### 3.1 冒烟测试
- 用最小输入起一个真实 K8s Job：`kubectl -n sciminer-model-jobs get pods -w`；
- 校验：Pod `Succeeded`、`result.json` 合法、产物路径均在 `/work/out`、`progress.json` 可读；
- 通过后再「设为当前版本」。

### 3.2 版本变更
- **已发布版本不可就地修改**；变更走「基于当前版本新建版本」：复制配置 → 改镜像/参数 → 填新版本号与变更说明 → 冒烟 → 发布。
- 旧版本可“弃用”（deprecated），历史版本保留可追溯。

---

## 4. 常见坑
1. `CUDA_VISIBLE_DEVICES` 写成宿主卡号（如 6）导致容器内 0 卡可见 → 用 `NVIDIA_VISIBLE_DEVICES=宿主卡号`，`CUDA_VISIBLE_DEVICES=0`。
2. 权重打进镜像 / 写死宿主路径 → 用 `runtime.weights.mounts`，产物只写 `/work/out`。
3. 忘记写 `result.json` 或写了绝对宿主路径 → 平台判失败。
4. 用 `latest` tag → 用 digest，保证可复现。
5. 显存需求超过 24GB（4090）→ 准入直接拒绝，换 DCU 或拆分模型。
6. 镜像未推 registry / pull secret 缺失 → Job `ImagePullBackOff`。
