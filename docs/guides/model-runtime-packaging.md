# Model Runtime Packaging Guide

本文档定义模型侧 Runtime Env 打包规则。平台契约固定，模型侧包适配平台输入、输出和运行环境；不要修改平台后端或前端来适配单个模型。

## 固定契约

- `MODEL_PACKAGE.yaml` 是模型侧元数据入口，声明模型版本、标准输入输出、Runtime Env、权重和缓存策略。
- `platform_run.sh` 是薄入口，只负责接收平台通用参数并调用模型侧 runtime CLI。
- 模型输出必须收敛为 `aidd.sciminer/result.v2`，由平台统一持久化标准 Artifact。
- Runtime Env 是可复现运行环境，不是某台机器上的私有 conda 路径。

## Runtime Env

- 首选产物是带镜像 digest 的 `container`，镜像 digest 必须进入 `MODEL_PACKAGE.yaml`。
- 受限集群可声明 `conda-pack` 或 venv-pack fallback，但必须提供 URI、SHA-256 和构建记录。
- `environment.yml`、`requirements.txt` 和 wheelhouse 只作为构建线索，不能替代已验证运行产物。
- Executor 不安装依赖，只选择已验证的 Runtime Env，挂载权重、输入目录、输出目录，然后执行 `platform_run.sh`。

## 平台注册与镜像责任

- 模型维护人员负责构建、验证并推送模型镜像；平台只管理管理员注册的 Tool Package 和 ToolVersion，不接收模型源码、权重包或本地构建目录。
- Tool Package v2 的主运行产物必须是 `container`，声明镜像地址和 `sha256:<64位十六进制>` digest。平台注册时按 digest 固定镜像引用，不接受管理员在注册请求中覆盖 manifest 或提交任意 Pod 配置。
- Tool Package 经管理员校验、签名并发布后，管理员才可从详情创建 Kubernetes 候选版本。注册不会切换现有当前版本；候选最新一次真实 Smoke 必须成功才能显式提升，后续失败会关闭提升门禁。
- Smoke 输入沿用任务输入契约：`params`、`file_ids`、`input_bindings`、`standard_input_uploads`。文件应先进入平台文件存储，Artifact 输入应绑定有效 ArtifactVersion。
- 版本提升只更新当前版本指针；旧版本保留，未废弃的旧 SSH 版本可用于回切。平台不负责适配单个模型，也不把 registry 凭据或 Kubernetes Secret 写入 Tool Package、镜像或 ToolVersion。

Smoke 成功依赖真实执行环境：执行后端需能提交并观察 K8s Job，节点需能拉取 digest 固定的镜像，Job 需能访问 MinIO 输入输出 bucket。Celery 执行模式还需部署集群 Worker。开发环境配置见 [Kubernetes 部署说明](../../deploy/kubernetes/README.md)。

## 打包边界

- 模型包可以修改 `original_model/` 内的兼容代码、runtime wrapper、测试和样例。
- 模型包不得提交真实密钥、账号、私有主机地址、宿主机绝对路径、权重文件或大体积缓存。
- 运行设备属于 Tool Package variant 或部署配置，不应作为用户必须填写的业务参数。
- 平台只消费标准 Artifact、参数 schema、Runtime Env 声明和 `result.v2`，不读取模型私有目录结构。

## 验证要求

每个模型包至少提供轻量合同测试，覆盖参数解析、输入文件发现、原始模型调用适配和 `result.v2` 输出结构。没有真实权重或硬件时，测试只能证明包装逻辑正确，不能声明科学效果或 GPU/DCU 兼容已经验证。
