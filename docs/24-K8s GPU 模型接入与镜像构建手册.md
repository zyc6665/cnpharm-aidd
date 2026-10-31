# K8s GPU 模型接入与镜像构建手册

| | |
|---|---|
| 文档编号 | DRP-MODEL-ONBOARD-K8S-v1.0 |
| 文档版本 | **v1.0**（2026-10-31，首个真机验证版：MolP-PC / MSIGN / Pocket2Mol 三模型经 4090 k3s 全链路跑通） |
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
| MSIGN | `aidd/compute-msign:1.0.0` | `d4e739c710a85dd5c289e4687f088c72540314886f4161bdb8587532ee8ab4f4` |
| Pocket2Mol | `aidd/compute-pocket2mol:1.0.0` | `f834fd01c614c531d861d55a32b2b60454575b12a3a04f861dc69d859a72dd26` |

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
   标准输入；MSIGN 需要 `protein_pdb` + `ligand_pdb`。
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
