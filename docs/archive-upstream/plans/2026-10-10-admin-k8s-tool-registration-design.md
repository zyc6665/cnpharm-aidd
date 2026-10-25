# 管理员 K8s 工具注册设计

> 状态：已获确认的设计方向；尚未实现。

## 目标

管理员可以把已发布 Tool Package 绑定为平台管理的 Kubernetes 工具版本。工具包提供模型运行契约和不可变镜像引用；平台只负责验证、绑定、资源档位准入和执行调度，不构建镜像、不修改模型、不替模型编写适配代码。

注册 K8s 版本不得覆盖正在工作的 SSH 版本。新版本先作为候选版本，完成管理员 smoke 后才能成为 Tool 的当前版本。

## 当前实现基线

- `ToolPackage` / `ToolPackageVersion` 保存包身份、manifest、manifest digest 和签名字段；发布路由要求 manifest 校验通过且签名字段非空。当前发布逻辑未执行密码学验签。
- Tool Package 详情页进入通用工具创建页；`mode=package` 默认选 `ssh_job`，把第一个 variant 的 entrypoint 填入 SSH 配置。
- 通用 K8s 表单只生成镜像和资源档位配置；`build_kubernetes_tool_config` 已有 digest、variant、executor 和档位校验，但未接入管理员注册 API。
- 创建 Tool 时，初始 ToolVersion 会直接成为当前版本。ToolVersion 可以保存 inactive 版本；当前版本指针由 `Tool.current_version_id` 控制。
- 普通任务可指定 `tool_version_id`，但当前加载逻辑未校验该版本属于请求中的 Tool，也未阻止普通用户使用 inactive/deprecated 版本。工作流固定解析 Tool 当前版本。
- 仓库中的 K8s Worker 是显式部署示例，不在默认 `deploy/kubernetes/kustomization.yaml` 中。是否已部署必须另查集群；不能从注册成功推断 K8s smoke 已通过。

## 领域设计

1. `ToolPackageVersion` 是模型交付来源，保存固定版本的 manifest、镜像引用和 digest。
2. `Tool` 是平台中的稳定工具身份；同一模型的 SSH 和 K8s 部署共用 Tool 身份。
3. `ToolVersion` 是一份不可变的执行绑定，包含 executor、包 manifest 快照、包来源标识、variant、digest 固定的镜像、entrypoint 和 Resource Profile。
4. 包版本与平台执行版本是不同概念。平台版本号标识运行配置修订，不能只复用包 semver；例如同一个模型包版本可以对应 SSH 和 K8s 两个 ToolVersion。
5. 首期不新增数据库表。来源快照存入 ToolVersion 的 JSON 配置；smoke 任务作为 Task 记录，并由服务端写入专用 `extra_data` 标记。
6. K8s 版本的资源档位必须以该 ToolVersion 的 Resource Profile 为准，不能改写或继承同一 Tool 上 SSH 版本的 Tool 级 GPU 字段。

K8s ToolVersion 配置的核心字段：

```json
{
  "type": "k8s_job",
  "variant": "cuda",
  "runtime": {
    "image": "registry.example/model:1.0.0@sha256:<64-hex>",
    "entrypoint": ["/app/platform_adaptor/entrypoint.sh"]
  },
  "resource_profile": "gpu-large",
  "tool_package_manifest": {},
  "tool_package_source": {
    "package_id": "...",
    "package_version_id": "...",
    "manifest_digest": "..."
  }
}
```

## 管理端接口

`GET /api/v1/tool-packages/{package_id}/kubernetes-options`

- 仅管理员可用，且受现有 Tool Package feature flag 控制。
- 返回当前已发布包版本 ID、可选 variant、已配置的 Resource Profile ID，以及同 slug 的现有 Tool 摘要。
- 档位列表从 `RESOURCE_PROFILE_REGISTRY_JSON` 读取；不接受前端自行定义的资源值。

`POST /api/v1/tool-packages/{package_id}/kubernetes-registrations`

请求只传选择项，不传 manifest：

```json
{
  "package_version_id": "...",
  "target_tool_id": "...",
  "category_id": "...",
  "tool_version": "1.0.0-k8s-cuda",
  "variant_name": "cuda",
  "resource_profile": "gpu-large"
}
```

- `target_tool_id` 存在时，后端要求目标 Tool 与包 slug 匹配；只新增候选 ToolVersion。
- 没有目标 Tool 时，管理员需提供分类；后端以包元数据创建 DRAFT Tool，再添加候选版本。
- 后端从数据库读取包版本，校验其归属、发布状态、manifest、digest、executor、variant、profile 和版本冲突；用既有 binding helper 生成运行配置。
- 创建 Tool（如需要）和 inactive ToolVersion 在同一数据库事务提交。现有 `current_version_id` 不变。
- 镜像不会由平台上传或构建。注册校验 digest 格式；镜像是否可拉取由后续实际 K8s smoke 验证。
- 现有签名门槛只检查签名字段存在；真正的密码学签名验证不属于本次注册功能，不应在 UI 中宣称已经完成。

## 候选验证与提升

`POST /api/v1/tools/{tool_id}/versions/{version_id}/smoke`

- 仅管理员可用；请求包含运行该模型所需的参数、文件和标准 Artifact 输入绑定。
- 服务端验证版本归属、executor 类型和候选状态，再调用现有任务准备/调度流程。
- 任务记录精确的 `tool_version_id`，服务端写入 smoke 用途标记；客户端不能伪造该标记。
- 这是真实模型镜像 smoke，不等价于仅检查 K8s 配置。UI 展示最新 smoke 任务状态和执行前置条件，不把 digest 校验误报为集群或镜像就绪探测。

`POST /api/v1/tools/{tool_id}/versions/{version_id}/promote`

- 仅管理员可用；目标版本必须属于 Tool 且未废弃。inactive 的 K8s 候选必须有同 Tool、同版本的最新 smoke 任务，且状态为 SUCCESS；最新 smoke 为 pending、running、failure 或 canceled 时均不得提升。
- 已 active 的旧版本（包括 SSH）可直接切回，不要求重新 smoke。
- 在一个事务内将候选版本设为 active 并切换 `current_version_id`；原 SSH 版本保留，可用于回滚。
- 普通任务必须校验版本属于请求 Tool，且只能执行允许的 active 版本；inactive 候选只可经管理员 smoke 路径执行。
- 工作流继续使用 `current_version_id`，无需增加 executor 选择逻辑。

## 管理端交互

Tool Package 详情页增加“注册 K8s 版本”入口。表单展示包版本和 manifest 摘要，管理员选择或确认目标 Tool、分类、平台版本号、variant 和资源档位。创建后显示候选状态、镜像 digest、smoke 任务状态和“提升为当前版本”操作；不在此流程中编辑模型契约或修改镜像。

## 明确不做

- 不移除或修改现有 SSH ToolVersion，不自动切换当前版本。
- 不在平台仓库保存模型代码或权重，不在平台构建/推送模型镜像。
- 不允许管理员向 Pod 注入任意 Kubernetes manifest、节点选择器、Secret 或凭证。
- 不把工作流改成按用户选择 executor；工作流仍运行当前版本。
- 不因 YAML 或配置存在就声称 MinIO、Worker、镜像仓库已经在目标集群实际就绪。
