# 中国医药 AI 药物研发平台 · 模型接入操作手册（SSH 直连与工具注册）


> **状态：已弃用（2026-10-31）。** 用户已明确不采用 SSH 直连；现行方案是 K8s+GPU
> 容器化接入，见 `docs/24-K8s GPU 模型接入与镜像构建手册.md`。本手册仅作历史参考。


| 项 | 内容 |
|---|---|
| 文档编号 | DRP-MODEL-ONBOARD-v1.0 |
| 文档版本 | **v1.0**（2026-10-31，首个真机验证版：MolP-PC / MSIGN / Pocket2Mol 三模型经平台 API 全链路跑通） |
| 上游 | `07-模型交付与运行规范.md`、`19-模型镜像构建与权重外置流程.md` |
| 适用范围 | 算力节点已存在、模型目录已就绪、平台通过 SSH 直连执行的模型接入（当前 4090 节点的接入方式） |

---

## 1. 三种接入方式，先选对

| 方式 | 平台执行器 | 适用条件 | 本期状态 |
|---|---|---|---|
| **A. SSH 直连（本手册）** | `ssh_job` | 算力节点已有模型目录 / conda 环境，暂不做镜像化 | ✅ 本手册主路径，已接入 3 个模型 |
| B. Tool Package v2 | `ssh_job` / `k8s_job` | 模型交付包带 `tool.yaml`（标准 Artifact 输入输出） | 已有包定义，平台配置尚未挂 `tool_package_manifest` |
| C. 容器镜像 | `k8s_job` / `docker_image` | 可离线构建镜像、有 GPU 调度 | 见 `docs/19`，DCU 真机未验证 |

> **原则**：先用 A 把模型跑通、把输入输出契约固定下来；需要横向扩容/多租户调度时再升级到 B/C。三种方式共用同一套任务、产物、审计链路。

---

## 2. 前置检查（缺一不可）

在算力节点（当前 4090：`10.202.2.228`，容器 `kaiwu`）上确认：

1. **模型目录**：例如 `/workspace/MSIGN`，含权重与推理代码；平台侧路径映射为容器内 `/workspace/<ModelDir>`。
2. **独立 conda 环境**：记录 `python` 绝对路径，写进工具配置 `env.MODEL_PYTHON`。
3. **包装脚本**：模型目录或版本目录下有 `platform_run.sh`，遵守平台约定：
   - 入参：`params.json`（平台上传），其中 `params` 为业务参数、`input_files` 为 `字段名 → input/<文件名>` 的相对路径；
   - 出参：`output/result.json`（必须含 `success`、`message`、`outputs`、`artifacts`、`metrics`）+ `output/artifacts/**`；
   - 日志：`output/logs/run.log`。
4. **SSH 免密**：平台后端 `backend/.ssh/ssh_4090_zhouyc`（私钥，文件名必须等于工具配置的 `auth_ref`）+ `known_hosts`；`backend/.env` 配 `SSH_AUTH_REF_DIR`、`SSH_KNOWN_HOSTS`。
5. **磁盘**：`remote_base_dir`（如 `/data/zhouyc/kaiwu/platform-jobs`）可写。

---

## 3. 新增一个模型：五步

### 第 1 步：在节点上把模型直接跑通（绕开平台）

```bash
# 在 kaiwu 容器内，用模型自己的环境
cd /workspace/<ModelDir>
<conda-python> platform_run.sh <任务目录>        # 或按模型 README 的 smoke 命令
```
先确认单机能产出 `result.json` 和 artifacts。**单机跑不通，平台一定跑不通。**

### 第 2 步：写工具注册文件

放在 `deploy/model-images/ssh-jobs/<slug>.json`（示例见同目录 `molp-pc.json`、`msign.json`、`pocket2mol.json`），关键字段：

```jsonc
{
  "name": "显示名",
  "slug": "kebab-case-slug",
  "category": "bioinformatics",
  "version": "0.1.0",
  "changelog": "接入说明",
  "tool_config": {
    "type": "ssh_job",
    "host": "10.202.2.228",
    "port": 22,
    "username": "zhouyc",
    "auth_ref": "ssh_4090_zhouyc",
    "runner_mode": "docker_exec",              // 或 ssh
    "remote_base_dir": "/data/zhouyc/kaiwu/platform-jobs",
    "entrypoint": "/workspace/<ModelDir>/platform_run.sh",
    "timeout_sec": 3600,
    "cleanup_remote": false,                    // 便于排障；确认稳定后可改 true
    "strict_host_key_checking": true,
    "env": { "PATH": "...", "MODEL_PYTHON": "/home/xxx/.conda/envs/<env>/bin/python" },
    "output_globs": ["output/result.json", "output/logs/run.log", "output/artifacts/**/*"],
    "input_schema": { "type": "object", "properties": { /* 文件字段 format=file */ }, "required": [] },
    "output_schema": { "type": "object" }
  }
}
```

**`input_schema` 是前端表单的唯一来源**：文件字段必须 `"format": "file"`，非文件参数给 `default`/`enum`/`minimum` 等约束。

### 第 3 步：注册到平台

```bash
cd backend
python ../scripts/create_tool.py --config ../deploy/model-images/ssh-jobs/<slug>.json
```

脚本会创建 `tools` + `tool_versions`（幂等：同名同版本已存在时按脚本逻辑处理），并输出 tool_id / version_id。

### 第 4 步：平台 E2E（API 层，推荐先跑）

```bash
cd backend
# 准备输入文件，然后：
python scripts/e2e_model_task.py --tool <tool_id> --version <version_id> \
  --file protein=<path> --file ligand=<path> \
  --params '{"distance":5.0,"device":"cpu"}'
```

或用最小 Python 脚本（与本次验证一致）：

```python
payload = {
  "name": "E2E",
  "tool_id": TOOL_ID,
  "tool_version_id": VERSION_ID,
  "params": {
    "params": {"distance": 5.0, "model_variant": "full_finetune", "device": "cpu"},
    "input_files": {"protein_pdb": protein_file_id, "ligand_pdb": ligand_file_id},
  },
  "file_ids": [protein_file_id, ligand_file_id],
}
requests.post(f"{BASE}/tasks", json=payload, headers={"X-CSRF-Token": csrf})
```

> **关键坑**：`input_files` 必须用**文件字段名 → 上传后的 file_id**，任务准备阶段会自动改写为 `input/<文件名>` 并把文件同步到节点。只传 `file_ids` 而不传 `input_files`，旧版 runner 会报
> `exactly one of input_files.ligand_file, input_files.ligand_pdb, or input_files.ligand_sdf is required`。
> 文件字段名必须与 runner 读取的键一致（MSIGN runner 认 `protein_pdb`/`ligand_pdb`，也兼容 `ligand_file`）。

轮询 `GET /api/v1/tasks/{id}`，终态为 `success`（注意：平台成功态是 `success`，不是 `completed`）。验收看三样：`status=success`、`result.success=true`、`output_file_ids` 非空。

### 第 5 步：UI 验证与交付

1. 打开「工具」页，确认新工具可见、输入表单按 `input_schema` 渲染（文件字段有上传框）。
2. 打开「任务」页，确认任务出现在列表、详情能看到输出文件与日志。
3. 把模型加入 `docs/07` §1.3 接入记录表，并在 `docs/18` 版本表记一条。

---

## 4. 本次已验证的三个模型（2026-10-31）

| 模型 | tool slug | entrypoint | 输入字段 | 验证结果 |
|---|---|---|---|---|
| MolP-PC 性质预测 | `molp-pc-property-prediction` | `/workspace/MolP-PC/platform_run.sh` | `smiles_csv` | 2 行输入 → 2 行预测，6.6s |
| MSIGN 亲和力预测 | `msign-affinity-prediction` | `/workspace/MSIGN/platform_versions/0.1.2/platform_run.sh` | `protein_pdb`、`ligand_pdb` | `predicted_affinity=-11.0999`，4.2s |
| Pocket2Mol 口袋生成 | `pocket2mol-pocket-ligand-generation` | `/workspace/Pocket2Mol-main/platform_run.sh` | `protein_pdb`（可选 `checkpoint_pt`） | 2 个分子，GPU `cuda:0`，61.4s |

三例均为：创建任务 → 平台 SSH 上传输入 → 节点容器执行 → 下载 `output/` → `result.json` 进入任务结果、artifacts 进入文件中心。

---

## 5. 常见错误对照表

| 现象 | 根因 | 处理 |
|---|---|---|
| `SSH auth_ref 'xxx' is not configured on worker node` | `backend/.ssh/<auth_ref>` 文件名不匹配 | 私钥文件名必须**完全等于** `auth_ref` |
| runner 报 `input_files.xxx is required` | 任务只传了 `file_ids`，没传 `params.input_files` 映射 | 按第 4 步构造 `input_files` |
| `ModuleNotFoundError` / 模型 import 失败 | `env.PATH` 或 `MODEL_PYTHON` 指错 conda 环境 | 节点上 `which python` 后写入配置 |
| 任务卡在 35% 长时间不动 | 模型推理本身慢，或 runner 未输出进度日志 | 看 `output/logs/run.log` 与 `progress_poll_interval_sec` |
| 任务 `failed` 但远端已生成结果 | 输出目录下载/收集失败 | 查后端日志的 `Failed to download SSH job outputs` |
| GPU 模型报 `cuda` 不可用 | `device` 传 `cpu`，或容器未挂 GPU | `device` 用 `cuda:0`；确认 `nvidia-smi` 在容器内可见 |

---

## 6. 新增模型 Checklist

- [ ] 节点单机 `platform_run.sh` 跑通，产出 `output/result.json`
- [ ] `deploy/model-images/ssh-jobs/<slug>.json` 写好，`auth_ref` 与私钥文件名一致
- [ ] `scripts/create_tool.py` 注册成功，拿到 tool_id / version_id
- [ ] API E2E `status=success`、`result.success=true`、`output_file_ids` 非空
- [ ] UI 工具页表单正常、任务页可查结果与日志
- [ ] `docs/07` §1.3 与 `docs/18` 版本表已登记
- [ ] 清理节点上的临时输入/输出（或确认 `cleanup_remote` 策略）

---

## 7. 后续扩展（更多模型接入时）

- **优先收敛为 Tool Package v2**：把 `tool.yaml` 的 `input_schema` 挂进工具配置的 `tool_package_manifest`，即可用标准 Artifact 输入（`input_bindings` / `standard_input_uploads`），不再依赖 `input_files` 旧映射。
- **容器化**：按 `docs/19` 把 conda 环境打成镜像，`type` 改 `k8s_job`/`docker_image`，获得资源配额与横向调度。
- **统一 smoke**：每个模型接入时用 `POST /api/v1/tools/{tool_id}/versions/{version_id}/smoke` 做候选版本冒烟，通过后再置为当前版本。
