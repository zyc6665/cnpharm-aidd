# 模型镜像构建与权重外置

本目录存放**已验证的模型镜像构建定义**。每个子目录对应一个模型，包含
`Dockerfile`、`requirements.txt`、`weights.json`（权重声明）与 `build.sh`。

模型代码与权重**不进仓库**——它们在构建机上，由 `build.sh` 从源目录准备。
所以本目录只占几 KB，但足以在任何一台有 docker 的机器上重建出同样的镜像。

## 为什么权重不进镜像

以 `lvpocket` 为例（实测）：

| 组成 | 大小 |
|---|---|
| 权重 `new_best/`（5 个 `.hdf`） | **19 GB** |
| Python 环境（TF 2.15 + CUDA 运行时） | 5.8 GB |
| 代码 + 数据（含 `psipred` 871 MB） | ~1 GB |
| **原样打包成镜像** | **26 GB** |
| **权重外置后的镜像** | **6.31 GB** |

两条理由：

1. **体积**。19 GB 权重 × 每个模型，镜像仓库会被塞满；而权重在推理时只读挂载，
   放镜像里没有收益。
2. **迭代**。换权重不应重新 build/push 一次镜像；权重要换版本时只需要改
   `weights.json` 里的 `urn` + `sha256`。

## 分层结构

```
base-cu121:py3.10-r3        ← CUDA/cuDNN/PyTorch 通用栈，整个平台只存一份
  └─ compute-<slug>:<ver>-cu121     ← 只叠加该模型的代码与专属依赖（几百 MB ~ 几 GB）

base-dtk26.04:py3.10-r3     ← DCU 侧同构的一套
  └─ compute-<slug>:<ver>-dtk26.04
```

base 镜像必须**显式版本化并冻结**（tag 里带 `py3.10-r3` 这类后缀）。否则各模型镜像
`pip install` 时装出不同版本的 torch，等迁移到 DCU 时无法定位差异。

## 镜像引用必须用 digest

`backend/app/execution/adapters/kubernetes_manifest.py` 强制要求
`image` 形如 `registry/repo@sha256:<64 hex>`（`docs/07` §3.6）。tag 可变，
digest 不可变——追溯包里记的镜像必须是「就是那一次跑的那个」。

```bash
docker push 127.0.0.1:30500/aidd/compute-lvpocket:2.0.0-cu122
docker image inspect 127.0.0.1:30500/aidd/compute-lvpocket:2.0.0-cu122 \
  --format '{{index .RepoDigests 0}}'
# → 127.0.0.1:30500/aidd/compute-lvpocket@sha256:daa60f56...
```

## 权重声明（`weights.json`）

对应 `tool-package.v2` manifest 的 `runtime.weights[]`：

```json
[
  {
    "name": "lvpocket-weights",
    "mountPath": "/opt/sciminer/model/new_best",
    "readOnly": true,
    "source": { "kind": "host-path", "path": "/data/zhouyc/model-cache/lvpocket/v2/new_best" },
    "cache":  { "kind": "host-path", "path": "/data/model-cache/lvpocket/2.0.0" }
  }
]
```

平台生成 Job 时：

- **节点缓存命中且 sha256 一致** → 直接 `hostPath` 只读挂载，零下载。
- **未命中** → 注入 downloader **initContainer**，从对象存储拉取、校验 sha256、
  解压到缓存路径，再挂给主容器。

两种路径都**不由模型自己下载**——`docs/07` §3.6 的 MD-02 明确禁止模型访问对象存储。
权重来源只有平台注入的挂载点。

`source.kind` 两种取值：

- `host-path`：开发期直接挂节点本地目录（无 sha256 校验，靠人工保证）。
- `object-store`：生产形态，带 `urn` + `sha256` + `sizeBytes`，由 initContainer 校验。

## 构建步骤

```bash
# 1. 准备构建上下文（把模型代码从源目录复制进 <MODEL>/model/）
#    源目录里的 env/ 不要带进来（那是 26G 里最大的部分之一，容器里重新 pip install）
export MODEL_SRC=/data/zhouyc/kaiwu/LVpocket-2
cd deploy/model-images/lvpocket
./build.sh prepare     # 调 rsync 拉 model/ 与 platform_adaptor/

# 2. 构建
./build.sh build

# 3. 验证（挂权重跑一次真实推理）
./build.sh smoke

# 4. 推送并记录 digest
./build.sh push
```

## 已构建的模型

| 模型 | 镜像 | 大小 | 验证状态 |
|---|---|---|---|
| `lvpocket`（口袋预测） | `compute-lvpocket:2.0.0-cu122` | 6.31 GB | ✅ 4090 GPU 跑通，17.35s，1 个口袋，10 个产物 |

## 相关文档

- `docs/19-模型镜像构建与权重外置流程.md` —— 完整流程、10 个适配问题与排查方法
- `docs/07` §1.1（`K100-AI` 已验证模型清单）、§3.6（runner 契约与 MD-02）
- `docs/03` §10（离线交付：镜像 + 权重包 + 内网 registry）
- `deploy/kubernetes/model-image-template/` —— 通用模板（本目录的实例由它演化而来）
