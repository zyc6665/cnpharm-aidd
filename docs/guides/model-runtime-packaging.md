# 模型运行环境打包指南

本文定义模型侧 Runtime Env 的固定规则。目标是让模型适配平台，而不是让平台为每个模型分叉。

## grill-me 结论

- 平台机器只做控制面、缓存和跳板，不作为模型代码、Python 环境或权重的唯一来源。
- 模型代码、Runtime Env 和权重必须是三个可版本化、可校验、可回滚的产物。
- Executor 不安装依赖，只选择已声明、已验证的 Runtime Env，并挂载输入、输出、工作目录和权重。
- 容器镜像是首选运行时；没有容器能力时才使用 conda-pack 或 venv-pack 作为 fallback。
- 所有缓存必须由模型版本、运行环境 digest、权重摘要和执行器类型共同决定，不能依赖可变宿主机路径。

## 标准产物

| 产物 | 责任 | Git 策略 |
| --- | --- | --- |
| Model Package | 原始模型源码、平台 wrapper、`platform_run.sh` 和轻量合同测试 | 提交源码、元数据、样例和测试 |
| Runtime Env | Python、CUDA runtime、系统库和 Python 依赖 | 不提交二进制环境，只在 `MODEL_PACKAGE.yaml` 记录引用和摘要 |
| Weights | 模型权重和权重 manifest | 不提交真实权重，只提交放置说明和校验要求 |

## Runtime Env 规则

`MODEL_PACKAGE.yaml` 的 `runtime` 字段必须至少声明：

- `python`：模型验证过的 Python 主版本。
- `environment_file` / `requirements_file`：环境重建线索，不等于生产运行时。
- `executor_support`：已验证的执行器后端，例如 `ssh_docker_exec`、`slurm`、`k8s_job`。
- `selection_policy`：执行器如何在多个 Runtime Env 之间选择，必须优先不可变镜像 digest。
- `artifacts.primary`：首选容器镜像，必须填写镜像名称和镜像 digest。
- `artifacts.fallback`：无容器场景的 conda-pack 或 venv-pack，必须填写 URI 和 SHA-256。
- `cache_policy`：缓存 key 必须包含模型版本、runtime digest 或 SHA-256、权重 manifest 摘要。

`environment.yml` 和 `requirements.txt` 只是构建 Runtime Env 的输入。生产执行时不允许要求管理员手工
`conda activate` 某个宿主机环境，也不允许在工具执行任务期间临时 `pip install` 或 `conda install`。

## 执行器矩阵

| Executor | 推荐运行方式 | 模型代码位置 | Runtime Env 位置 | 权重位置 |
| --- | --- | --- | --- | --- |
| `ssh_docker_exec` | 远端拉取或预热容器镜像后执行 `platform_run.sh` | 远端缓存的模型包版本目录 | 容器镜像 digest | 远端缓存或挂载目录 |
| `slurm` | 优先 Apptainer/Singularity 容器，其次 conda-pack 解包 | 共享存储或作业临时目录 | 镜像 SIF 或 conda-pack | 共享存储或作业预取 |
| `k8s_job` | Pod 使用模型 Runtime 镜像，init step 拉取模型包和权重 | init step 写入工作卷 | Pod 镜像 digest | PVC、对象存储或 init step 缓存 |

执行器只负责把标准输入文件、输出目录、工作目录、参数 JSON 和设备上下文传给 `platform_run.sh`。
`platform_run.sh` 不感知它是在 SSH、Slurm 还是 K8s 中运行。

## 部署检查

部署一个新模型工具时，必须记录：

- 模型包版本和源码提交。
- Runtime Env 类型、镜像 digest 或 conda-pack SHA-256。
- 权重 manifest 和每个大文件的 SHA-256。
- CPU/GPU 型号、驱动版本、CUDA 兼容性和执行器类型。
- 使用的标准输入样例、输出 `result.v2` 和产物哈希。

缺少这些信息时，只能声明“包装合同测试通过”，不能声明“生产运行环境已验证”。
