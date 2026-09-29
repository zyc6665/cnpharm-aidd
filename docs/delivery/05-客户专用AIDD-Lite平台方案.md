# 客户专用 AIDD Lite 平台方案

| 文档项 | 内容 |
| --- | --- |
| 文档编号 | SCI-LITE-DES-001 |
| 文档版本 | v0.2 |
| 文档状态 | 方案草案 |
| 编制日期 | 2026-09-09 |
| 修订日期 | 2026-09-25 |
| 适用系统 | 客户专用 AIDD Lite 平台 |
| 来源基线 | 从现有 AI 制药研发平台裁剪独立 repo 交付 |

## 1. 方案定位

本方案面向单一企业客户的专用 AIDD 平台交付。客户需求不是建设一个可长期开放扩展的通用工具平台，而是在固定模型、固定计算工具和固定业务流程下，交付一个部署简单、使用直接、运维成本低的研发工作台。

平台交付后默认不支持客户通过管理后台新增、删除或修改模型。模型、权重、运行环境、工具参数和工作流模板随平台版本一起发布。后续如需替换模型或增加工具，应通过代码版本升级和交付包升级完成，而不是通过线上动态注册完成。

### 1.1 核心目标

- 固定集成若干深度学习模型和分子计算工具。
- 支持单工具运行和预置工作流运行。
- 简化部署，减少模型环境、权重和外部服务配置步骤。
- 保留任务队列、日志、取消、结果回收和 Artifact 管理能力。
- 去除 Agent、动态 Tool 注册、管理员模型发布审核、多租户治理等复杂能力。

### 1.2 非目标

- 不做通用模型市场或工具市场。
- 不支持业务管理员在线上传新模型并发布。
- 不做 Agent 自动规划、自动执行审批和自然语言编排。
- 不做多租户计费、跨组织资源治理和复杂权限矩阵。
- 不把运行成功包装成模型科学验证结论。

## 2. 推荐结论

可以把模型内嵌在平台交付包中，但这里的“内嵌”应定义为：模型代码、权重、运行环境和工具契约作为平台固定资产随版本交付，而不是把推理过程放进 Web/API 进程中同步执行。客户生产部署以集团 Kubernetes 集群为运行环境，所有模型和计算工具任务统一通过 Kubernetes Job 执行，不部署常驻模型推理服务。

推荐做法是：

- 模型和计算工具作为内置 Tool Runtime 随 repo 或镜像交付。
- Backend 只负责鉴权、参数校验、任务创建、工作流编排和结果索引。
- K8s Adapter Worker 负责把平台任务提交为 Kubernetes Job 并同步状态；计算 Pod 执行模型推理、GROMACS、RDKit 等任务。
- 平台逻辑队列负责业务优先级和并发准入；Kubernetes Scheduler 负责节点和硬件资源分配。
- Artifact Storage 负责保存输入快照、输出文件、日志、报告和谱系。

这种方案让模型、依赖和硬件资源通过不可变镜像及 Job 资源声明交付，不需要独立注册模型服务。模型冷启动和镜像拉取会增加单次任务启动时间，需通过镜像预热、权重缓存和合理的任务批量来控制。

## 3. 裁剪后的总体架构

```text
用户浏览器
  │
  ▼
Frontend
  │
  ▼
Backend API
  ├─ Project / File / Artifact API
  ├─ Built-in Tool API
  ├─ Task API
  └─ Workflow API
      │
      ▼
Task / Workflow Service
  ├─ 参数校验
  ├─ 输入绑定
  ├─ 任务创建
  ├─ 状态同步
  └─ 结果索引
      │
      ▼
平台 Queue / Task Scheduler
  ├─ cpu_light
  ├─ gpu_inference
  └─ md_heavy
      │
      ▼
K8s Adapter Worker (Deployment)
  ├─ 创建 / 查询 / 取消 Job
  ├─ 同步状态和日志
  └─ 回收并校验输出
      │
      ▼
Kubernetes Job / Pod
  ├─ DL Model Runtime
  ├─ GROMACS Runtime
  ├─ RDKit Runtime
  └─ Report Runtime
      │
      ▼
Artifact / Result Storage
```

平台和 Kubernetes 的职责边界：平台按固定工具配置选择逻辑队列、执行器和资源画像，并执行项目级准入、并发控制和任务生命周期管理；Kubernetes 根据 Pod 的 requests/limits、节点标签、污点和配额进行实际节点调度。平台可以观测 Job、Pod、Events 及经授权的集群指标，但不自行挑选节点，也不承诺精确预测任务何时获得资源。

### 3.1 与通用平台的主要区别

| 能力 | 通用平台 | AIDD Lite 平台 |
| --- | --- | --- |
| 工具来源 | Tool Contract 动态注册和发布 | 固定内置工具清单 |
| 模型变更 | 管理员审核后发布 ToolVersion | 通过代码和交付包升级 |
| Agent | 支持计划、解释、审批 | 不包含 |
| 工作流 | 用户可自由编排和保存 | 以预置模板为主，允许有限参数化 |
| 执行器 | `k8s_job`、`ssh_job` 以及兼容 runtime | 客户生产环境统一使用 `k8s_job`；无集群环境使用受控 `ssh_job`，本地 runner 不作为客户生产执行路径 |
| 权限 | 多角色、多项目、治理审计 | 项目级权限和基础审计 |
| 运维复杂度 | 面向扩展和治理 | 面向稳定交付和易部署 |

## 4. Repo 拆分建议

建议从现有平台新建一个客户专用 repo，例如 `aidd-lite-customer-platform`。新 repo 不应简单复制全部通用平台功能，而应按交付目标裁剪目录和依赖。

```text
aidd-lite-customer-platform/
  backend/
    app/
      api/
      tasks/
      workflows/
      artifacts/
      builtin_tools/
      settings/
  frontend/
    src/
      views/
        tools/
        workflows/
        tasks/
        artifacts/
  tools/
    rdkit/
    gromacs/
    report/
  model-bundles/
    model-a/
      MODEL_PACKAGE.yaml
      platform_run.sh
      src/
      weights/
      examples/
    model-b/
      MODEL_PACKAGE.yaml
      platform_run.sh
      src/
      weights/
      examples/
  workflow-presets/
    admet_screening.yaml
    docking_md.yaml
  deploy/
    docker-compose.yaml
    env.example
    nginx.conf
  docs/
    delivery/
    operations/
```

### 4.1 建议保留

- 文件上传、文件下载和 Artifact 版本记录。
- 任务创建、排队、运行、取消、重试、日志和结果回收。
- 内置工具参数 schema 和输入输出 schema。
- 工作流模板、节点状态、上游输出到下游输入的自动绑定。
- 基础项目权限和审计日志。
- 运行环境健康检查和队列监控。

### 4.2 建议删除或关闭

- Agent 对话、计划、审批和自动编排。
- 新建工具的 Remote API 自注册；历史 Remote API 工具仅在迁移确有需要时兼容导入。
- 管理员动态创建工具、修改模型、发布 ToolVersion 的页面。
- 通用 Governance Registry 中面向多租户和工具市场的配置项。
- 不属于客户固定流程的工具模板、演示模板和历史兼容适配。

## 5. 内嵌模型设计

### 5.1 内嵌资产范围

每个模型按固定模型包交付：

- `MODEL_PACKAGE.yaml`：声明模型名称、版本、输入输出、资源需求和运行环境。
- `platform_run.sh`：统一执行入口。
- `src/`：模型侧 wrapper，负责输入转换、调用旧模型、输出标准结果。
- `weights/`：权重文件或权重 manifest。
- `examples/`：最小输入、期望输出和 smoke test 样例。
- `docs/`：模型卡、适用范围、限制、验证记录和硬件说明。

模型包内部可以保留旧模型代码，但旧模型私有参数、临时文件名和输出格式不应泄漏到平台工作流层。平台只面对标准输入、标准输出和固定参数 schema。

### 5.2 三种内嵌方式

| 方式 | 描述 | 优点 | 风险 | 推荐场景 |
| --- | --- | --- | --- | --- |
| 镜像内嵌 | 模型代码、依赖、权重打入专用 runtime 镜像 | 部署最简单，环境最稳定 | 镜像较大，更新需重新发版 | 首选生产交付 |
| repo 内嵌 + 挂载权重 | 模型代码在 repo，权重部署时挂载 | 代码可读，权重可独立管理 | 环境一致性较弱 | 开发、联调、内网交付 |
| 对象存储内嵌 manifest | repo 固定 manifest，首次启动拉取权重和环境包 | 交付包较小 | 依赖对象存储和 checksum 校验 | 权重较大、客户内网有制品库 |

推荐默认采用“镜像内嵌 + manifest 校验”。即每个模型有不可变镜像 digest，权重有 checksum，平台启动时只检查资产是否存在和版本是否匹配。

### 5.3 不建议的做法

- 不建议把 PyTorch/TensorFlow 模型直接加载在 API 进程里长期驻留。
- 不建议让前端或工作流节点理解模型私有文件名。
- 不建议依赖某台机器上的 conda 路径作为生产运行契约。
- 不建议用一个万能 Python 环境跑所有模型和 GROMACS。
- 不建议跳过输入快照、日志和输出 manifest，直接把文件散落在任务目录。

## 6. 推理和计算调度设计

### 6.1 调度原则

所有推理和计算任务都经过平台任务系统，并由 K8s Adapter 创建独立 Kubernetes Job。客户部署不使用常驻模型 Deployment，也不在 API 或 Celery Worker 进程中直接运行模型。

核心原则：

- API 进程只创建任务，不执行重计算。
- K8s Adapter Worker 按平台队列消费任务并提交 Job；它不运行模型计算本身。
- 不同资源类型分队列，避免重任务阻塞轻任务。
- 每个任务尝试对应一个独立 Job/Pod、输入快照、输出前缀和日志；重试创建新的 Job。
- 输入输出通过对象存储或客户批准的共享存储传递，不依赖 Pod 本地磁盘作为持久结果。
- 执行完成后校验 result manifest，再持久化 Artifact；完成结果收集前不清理 Job 及输出。

### 6.2 推荐队列

| 队列 | 任务类型 | 并发建议 | 说明 |
| --- | --- | --- | --- |
| `cpu_light` | 文件转换、RDKit 描述符、小表格处理 | 按 Namespace 配额和平台并发上限配置 | 仍使用独立 Job；以准入和并发上限控制大量短任务 |
| `gpu_inference` | 深度学习模型推理、批量打分 | 按 GPU 配额、GPU 类型和客户并发策略配置 | Job 声明 GPU 资源；由 Kubernetes Scheduler 分配节点 |
| `md_heavy` | GROMACS 能量最小化、MD、长时模拟 | 按 CPU/内存/时长配额配置 | 独立 Job，设置 deadline，支持取消和状态恢复 |
| `report` | 结果汇总、图表、PDF/HTML 报告 | 按 Namespace 配额和平台并发上限配置 | 使用独立 Job；不阻塞 API 和计算任务 |

队列是平台的业务隔离和流量控制层，不是 Kubernetes 节点队列的替代品。平台应限制同时创建和运行的 Job 数量，并对各队列设置等待上限；Job 创建成功但 Pod Pending 时，任务保持资源等待状态并展示可读原因。

### 6.3 单模型推理流程

```text
用户选择模型工具并提交输入
  -> Backend 校验参数和输入类型
  -> 创建 Task 和 attempt，记录输入/参数/工具版本快照
  -> 根据固定资源画像选择 gpu_inference 或 cpu_light 逻辑队列
  -> K8s Adapter Worker 创建带 task_id/attempt_id 标签的 Job
  -> Kubernetes Scheduler 根据 requests、GPU、节点标签和配额选择节点
  -> Job Pod 从对象存储或共享存储读取输入
  -> platform_run.sh 读取标准 request
  -> 模型 wrapper 调用真实推理代码
  -> 输出 result.v2、artifact 文件和日志到持久化存储
  -> Adapter 校验输出、收集日志并更新 Task / Artifact
  -> Job 完成且结果已回收后按 TTL 清理
  -> 前端展示结果、日志、下载入口和失败原因
```

### 6.4 GROMACS 计算流程

```text
用户提交结构、参数和模拟模板
  -> Backend 校验输入文件、参数范围和资源预估
  -> 创建 Task 并进入 md_heavy 队列
  -> K8s Adapter 创建有 CPU/内存/时长限制的 Job
  -> GROMACS Pod 从持久化输入准备独立 workdir
  -> GROMACS Runner 生成 mdp/top/gro/tpr 等运行文件
  -> 执行 grompp/mdrun 等步骤
  -> 增量写入日志和进度
  -> 用户可取消任务，Adapter 删除 Job 并等待 Pod 终止
  -> 输出 trajectory、energy、log、summary report 到持久化存储
  -> Adapter 校验并登记 Artifact，之后清理 Job
```

GROMACS Job 与模型 Job 通过不同逻辑队列、并发上限和资源画像隔离；实际节点仍由 Kubernetes Scheduler 选择。

### 6.5 Kubernetes Job 生命周期

```text
Task queued
  -> Job submitted
  -> Pod Pending / Running
  -> Job Succeeded -> collect and validate outputs -> Task succeeded
  -> Job Failed -> collect diagnostics -> retry as a new attempt or Task failed
  -> User cancellation -> delete Job -> wait for Pod termination -> Task cancelled
```

状态同步以 Kubernetes Job/Pod 状态为执行事实来源，以平台数据库为业务任务和 Artifact 的事实来源。Adapter 需要支持周期性 reconcile：进程重启后根据持久化的 namespace、job_name 和 attempt_id 找回 Job；Kubernetes API 暂时不可达时保留待检查状态，不可直接把任务标记成功或失败。Job/Pod 必须带平台任务、尝试次数和工具版本标签，日志和 Events 按相同标识归档。

推荐 Job 默认策略：`restartPolicy: Never`、`backoffLimit: 0`，由平台统一控制重试；设置与工具超时对应的 `activeDeadlineSeconds` 和结果收集窗口。平台确认日志、result manifest 和 Artifact 已回收后，才允许 `ttlSecondsAfterFinished` 清理已完成 Job。取消采用有界宽限期，宽限期后强制删除 Job/Pod，并以底层终止结果确认平台取消状态。

### 6.6 K8s 资源与镜像映射

工具资源画像由固定配置维护，不接受普通用户提交任意镜像、命令、Namespace 或节点约束。Adapter 将 CPU、内存和 GPU 需求映射为 Pod `resources.requests/limits`，并套用管理员配置的 Namespace、节点标签、污点容忍、优先级和存储策略。`gpu_memory_mb` 只能作为工具准入或节点类型选择的辅助元数据，Kubernetes 通常不能据此直接切分和调度普通 GPU；GPU 型号和数量应使用集群安装的 Device Plugin 暴露的扩展资源及节点标签表达。

镜像必须来自客户批准的内网 Registry，并固定到 digest；GPU Job 使用的驱动、Device Plugin、CUDA/ROCm/DTK 及模型镜像组合需针对目标硬件完成 smoke test。GPU 不足、配额不足或节点约束不匹配时，Job 可以保持 Pending，由平台显示 Pending 时长和可用的调度事件，不应绕过集群策略改投未验证硬件。

### 6.7 工作流节点执行规则

工作流每个节点创建一个独立 Task attempt 和 Kubernetes Job。节点间只传递已持久化并通过 manifest 校验的 Artifact 引用，不依赖前一 Pod 的本地目录。上游节点失败时暂停依赖节点；用户重试节点时创建新的 Job，并保留旧 attempt 的日志和输出以便审计。

### 6.8 工作流运行流程

```text
用户选择预置工作流模板
  -> 上传初始输入并填写少量参数
  -> Backend 展开 workflow preset
  -> 对每个节点做输入 readiness 检查
  -> ready 节点创建 Task 并入对应逻辑队列
  -> Adapter 为节点创建独立 Kubernetes Job
  -> 节点完成后将 Artifact 自动绑定到下游节点
  -> 下游节点读取上游 Artifact 后创建自己的 Job
  -> 任一节点失败时暂停后续依赖节点
  -> 用户查看失败日志，可重试失败节点
  -> 全部完成后生成汇总报告
```

工作流层只表达固定节点、依赖关系、参数透传和结果绑定，不复制每个工具的私有规则。

## 7. Built-in Tool 设计

由于客户版不需要动态新增工具，可以将工具清单作为代码和配置固定下来。

### 7.1 工具定义

每个工具使用一份静态定义：

```yaml
slug: admet-predictor
name: ADMET Predictor
version: 1.0.0
kind: builtin_model
executor: k8s_job
entrypoint: model-bundles/admet/platform_run.sh
queue: gpu_inference
inputs:
  - name: molecules
    type: molecule_table@1
outputs:
  - name: predictions
    type: molecule_table@1
parameters_schema:
  type: object
  properties:
    batch_size:
      type: integer
      default: 128
resources:
  cpu: "8"
  memory: 32Gi
  accelerator: nvidia
  gpu_count: 1
  gpu_memory_mb: 16000
  timeout_sec: 3600
node_selector:
  accelerator-class: approved-gpu
```

`node_selector`、tolerations、PriorityClass、Namespace、镜像拉取凭据和存储挂载策略属于部署侧受控配置，工具 manifest 只引用经批准的资源档位，不直接指定客户节点名称。平台展示的资源预检是静态画像与 Namespace 配额摘要，不等价于 Kubernetes 对具体 Job 的调度承诺。

### 7.2 工具加载方式

推荐启动时读取 `tools/builtin_tools.yaml` 或数据库 migration 初始化工具清单。工具对用户可见，但不提供后台编辑入口。

允许研发团队通过发版修改工具定义。发版时必须跑 contract test、smoke test 和核心工作流测试。

## 8. 前端产品形态

前端也需要同步裁剪。AIDD Lite 不是只把后端能力关掉，而是要把用户可见入口、路由、导航、状态管理和接口调用都收敛为“固定模型研发工作台”。否则即使后端不支持动态模型，前端仍保留工具创建、工具发布、Agent、研究白板和复杂管理入口，会让交付范围显得不清晰，也会增加验收和维护成本。

前端设计目标是：用户打开平台后只看到项目、固定工具、预置工作流、任务和结果，不看到模型治理、工具市场、Agent 自动规划或通用科研白板。

### 8.1 前端裁剪原则

- 导航只保留客户会实际使用的入口。
- 固定工具以“功能模块”展示，不以“可扩展工具市场”展示。
- 工作流以预置模板运行和结果跟踪为主，不鼓励自由拖拽无限组合。
- 参数表单来自内置工具 schema，但用户不能编辑工具 schema。
- 前端不保存模型运行规则，模型输入输出规则仍以后端和工具契约为准。
- 任务状态、日志、取消、重试和下载必须保留为一等能力。
- 管理类能力只保留系统健康、队列状态和基础账号配置。

### 8.2 推荐信息架构

```text
AIDD Lite Frontend
  ├─ 工作台
  │   ├─ 最近任务
  │   ├─ 最近结果
  │   ├─ 常用单工具入口
  │   └─ 预置工作流入口
  ├─ 项目
  │   ├─ 项目总览
  │   ├─ 项目文件
  │   ├─ 项目结果
  │   └─ 项目任务
  ├─ 工具
  │   ├─ ADMET / 属性预测
  │   ├─ 结构准备
  │   ├─ Docking / 打分
  │   ├─ GROMACS / MD
  │   └─ 报告生成
  ├─ 工作流
  │   ├─ 模板选择
  │   ├─ 输入配置
  │   ├─ 运行状态
  │   └─ 结果汇总
  ├─ 任务
  │   ├─ 任务列表
  │   ├─ 任务详情
  │   ├─ 日志
  │   └─ 失败诊断
  ├─ 结果
  │   ├─ Artifact 列表
  │   ├─ 表格/结构/轨迹/报告预览
  │   └─ 下载
  └─ 系统
      ├─ 队列状态
      ├─ Worker 健康
      └─ 版本信息
```

### 8.3 路由裁剪建议

| 路由 | Lite 处理 | 说明 |
| --- | --- | --- |
| `/` | 重定向到 `/workspace` 或登录页 | 不需要品牌营销首页 |
| `/workspace` | 保留并改为客户工作台首页 | 展示常用工具、预置工作流、最近任务 |
| `/projects/:projectId` | 保留 | 项目总览、文件、结果、任务聚合 |
| `/projects/:projectId/settings` | 简化保留 | 只保留项目名称、成员、归档等基础配置 |
| `/projects/:projectId/lineage` | 可保留 | 若客户重视复现和审计，保留 Artifact 谱系 |
| `/tools` | 保留但改名为“工具运行” | 展示固定内置工具，不展示发布、审核、创建入口 |
| `/tools/:id` | 保留 | 单工具详情和运行表单 |
| `/workflow` | 保留并改为“工作流模板” | 以模板选择和运行为主 |
| `/workflow/runs/:runId` | 保留 | 工作流运行详情、节点日志和结果 |
| `/tasks` | 保留 | 任务中心 |
| `/tasks/:id` | 保留 | 任务详情、日志、下载、取消、重试 |
| `/user/settings` | 简化保留 | 账号、密码、偏好设置 |
| `/admin/*` | 默认删除 | 不保留通用管理后台 |
| `/system` 或 `/ops` | 可新增轻量运维页 | 只展示健康、队列、版本，不提供模型增删改 |
| `/projects/:projectId/research/*` | 删除 | Agent/会话能力不交付 |
| `/research-boards/*` | 删除 | 通用科研白板不属于固定模型平台 |
| `/admin/tools/create`、`/admin/tools/:id/edit` | 删除 | 禁止在线创建或编辑模型工具 |
| `/admin/tool-packages` | 删除 | Tool Package 通过发版交付，不在线发布 |
| `/admin/tool-categories`、`/admin/workbench-groups` | 删除 | 分类和分组固化在代码配置中 |

### 8.4 导航裁剪建议

主导航建议只保留：

- 工作台
- 项目
- 工具运行
- 工作流
- 任务
- 结果
- 系统状态

应从侧边栏和命令面板移除：

- 研究白板
- Agent / 项目研究
- 管理后台
- 工具创建
- 工具包发布
- 工具分类管理
- 工作台分组管理

命令面板如保留，只允许搜索项目、任务、结果、固定工具和工作流模板，不能暴露已裁剪的隐藏路由。

### 8.5 页面保留和改造

建议保留：

- 工作台页：从通用 dashboard 改为“开始一次计算”的入口，包含固定工具卡片、工作流模板卡片、最近任务和最近结果。
- 项目总览页：保留项目资产聚合，但去掉 Agent 建议、会话入口和复杂活动流。
- 工具列表页：改为固定工具启动台，按药研任务分组，例如 ADMET、结构准备、Docking、MD、报告。
- 工具详情页：保留参数表单、输入选择、示例填充和运行按钮；删除工具编辑、发布状态流转和管理员提示。
- 工作流页：从自由编排画布收敛为模板化运行。可以保留画布作为状态展示，但不提供任意新增工具节点能力。
- 工作流运行详情页：保留节点状态、日志、失败节点重试、上游下游结果绑定和汇总报告。
- 任务列表页：保留筛选、搜索、状态、队列、耗时、用户和项目维度。
- 任务详情页：保留日志、输入快照、输出 Artifact、失败诊断、取消和重试。
- Artifact/结果页：保留表格、结构、口袋、轨迹、报告预览和下载。
- 系统状态页：从管理后台中拆出轻量只读页面，展示 API、平台队列、K8s Adapter、Job/Pod 汇总状态、存储和模型 runtime 版本；集群指标仅显示客户已授权且已接入的摘要。

建议删除：

- Agent 对话页。
- Agent 事件流、计划审批卡片和会话侧栏。
- 项目研究页。
- 研究白板列表和画布。
- 工具发布审核页。
- 动态 Tool Contract 编辑页。
- Tool Package 上传、校验和发布页。
- 复杂治理注册表配置页。
- 面向多租户的全局管理看板。
- 用户收藏、工具市场推荐、复杂标签治理等非首期交付入口。

### 8.6 前端模块保留和删除

| 模块区域 | 保留 | 删除/裁剪 |
| --- | --- | --- |
| `views/workspace` | 保留，改为 Lite 首页 | 删除 Agent 推荐和复杂平台概览 |
| `views/tools/List.vue` | 保留，改为固定工具启动台 | 删除动态创建、发布状态管理入口 |
| `views/tools/Detail.vue` | 保留，作为单工具运行页 | 删除编辑入口和管理员发布动作 |
| `views/tools/Create.vue` | 删除 | Lite 不支持前端创建工具 |
| `views/workflow` | 保留，收敛为模板运行和运行详情 | 删除自由工具市场式节点选择 |
| `components/workflow` | 保留运行、预检、结果、状态组件 | 删除或隐藏 `AiddAgentPanel` 和任意工具新增入口 |
| `views/tasks` | 保留 | 只裁剪与 Agent 计划关联的展示 |
| `components/tasks` | 保留 | 按固定 Artifact 类型精简展示分支 |
| `components/artifacts` | 保留 | 可按客户文件类型删除无用 renderer |
| `views/projects/Research.vue` | 删除 | 属于 Agent/会话能力 |
| `components/conversation` | 删除 | 属于 Agent/会话能力 |
| `views/research-boards` | 删除 | 不属于固定模型平台 |
| `components/research-boards` | 删除 | 不属于固定模型平台 |
| `views/admin` | 默认删除 | 可拆出只读 `views/system/Status.vue` |
| `domain/tool-packages` | 删除或仅保留 manifest 类型 | 不保留发布 readiness 和编辑逻辑 |
| `domain/admin` | 删除大部分 | 仅保留系统健康展示模型 |
| `api/conversations.ts`、`api/agent-stream.ts` | 删除 | 不调用 Agent 后端 |
| `api/tool-packages.ts` | 删除或改为内部构建工具 | 用户侧不需要 |
| `stores/project-conversation.ts` | 删除 | 不保留项目会话 |
| `composables/useAgentEventStream.ts` | 删除 | 不保留 Agent 事件流 |

### 8.7 工作流前端形态

推荐采用“模板驱动工作流”，而不是保留完整自由编排工具。

```text
模板列表
  -> 选择模板
  -> 展示固定流程图和输入要求
  -> 用户上传文件 / 选择已有 Artifact
  -> 用户填写少量参数
  -> 预检
  -> 提交运行
  -> 节点状态跟踪
  -> 失败节点重试或取消
  -> 输出汇总报告
```

如果保留画布，画布主要承担展示职责：

- 展示固定节点和依赖关系。
- 展示每个节点的 running、success、failed、skipped 状态。
- 点击节点查看输入、输出、日志和重试按钮。
- 不提供任意添加工具、不提供任意连线、不暴露 Tool Contract 细节。

这样可以复用现有工作流组件，又不会把客户版做回通用平台。

### 8.8 单工具前端形态

单工具运行页应像“计算表单”，而不是“工具详情市场页”。

页面结构建议：

- 工具说明：用途、输入要求、输出说明、模型版本和限制。
- 输入区：上传新文件或选择项目已有 Artifact。
- 参数区：只展示客户可调参数，隐藏运行环境、executor、路径和模型权重配置。
- 预检区：显示输入是否满足、预计资源、队列和预计耗时。
- 运行区：提交任务后跳转任务详情或嵌入运行状态。
- 结果区：成功后展示核心结果、报告和下载入口。

### 8.9 前端状态和接口收敛

Lite 前端应减少全局状态数量，避免保留通用平台的隐性复杂度。

建议保留的 store：

- `user`：登录用户和基础权限。
- `app`：主题、侧边栏、全局错误。
- `projects`：项目列表和当前项目。
- `tools`：固定工具清单和工具详情，只读。
- `tasks`：任务列表、详情、日志和状态同步。
- `artifacts`：Artifact 列表、详情、下载。
- `workflow-definitions` / `workflow-runs`：模板定义和运行实例。

建议移除或拆薄的 store/composable：

- Agent 会话、Agent event stream、Plan approval 相关状态。
- Tool Package 发布 readiness 相关状态。
- 管理后台 taxonomy、workbench group、tool category 编辑状态。
- 研究白板 canvas 状态。

### 8.10 前端验收点

前端裁剪完成后，应按以下口径验收：

1. 普通用户看不到 Agent、研究白板、工具创建、工具编辑和工具包发布入口。
2. 浏览器直接访问被裁剪路由时返回 404 或重定向到工作台。
3. 固定工具列表只展示交付范围内工具。
4. 单工具运行能完成上传、参数填写、预检、提交、状态查看和结果下载。
5. 工作流模板能完成选择、输入配置、预检、运行、节点状态查看和失败重试。
6. 任务中心能筛选 `cpu_light`、`gpu_inference`、`md_heavy` 等队列任务。
7. 系统状态页只读展示健康和版本，不允许修改模型、工具或运行环境。
8. 前端构建产物不再引用已删除的 Agent、Admin 工具治理和研究白板模块。

## 9. 部署形态

### 9.1 本地开发版

仅用于开发和合同测试，不作为客户生产部署形态。可以使用本地 runner 验证 Tool Contract，但生产验收必须通过 Kubernetes Job 路径。

```text
一台 Linux 服务器
  ├─ Nginx
  ├─ Frontend Static
  ├─ Backend API
  ├─ PostgreSQL 或 SQLite
  ├─ Redis
  ├─ MinIO 或 local storage
  └─ 本地兼容 runner（非生产路径）
```

本地模式不证明集群调度、GPU 分配、RBAC、共享存储、Job 取消或节点故障恢复已通过验收。

### 9.2 私有服务器版

适合客户有独立 GPU 服务器或计算节点的场景。

```text
Web/API 节点
  ├─ Nginx
  ├─ Frontend
  └─ Backend

数据节点
  ├─ PostgreSQL
  ├─ Redis
  └─ MinIO

计算节点
  └─ runtime images / model bundles（仅用于开发或联调）
```

该形态可用于集群环境不可用时的开发/联调，不属于本客户目标生产形态。客户交付环境统一按下节 Kubernetes 集群版验收。

### 9.3 客户 Kubernetes 集群版（生产基线）

客户提供集团内部 Kubernetes 集群，平台控制面与计算 Job 部署在集群内或按客户网络规范访问该集群。所有固定模型、RDKit、Docking、GROMACS 和报告工具统一通过 Kubernetes Job 执行，不部署常驻模型推理 Deployment。

```text
Namespace: aidd-platform
  ├─ Frontend / Ingress
  ├─ Backend API (Deployment)
  ├─ K8s Adapter Worker (Deployment, platform queues)
  ├─ Redis (Deployment 或客户托管服务)
  └─ PostgreSQL / Object Storage (优先使用客户托管服务)

Namespace: aidd-compute
  ├─ CPU tool Jobs
  ├─ GPU model Jobs
  └─ GROMACS / Docking Jobs
       ├─ 固定镜像 digest
       ├─ CPU / memory / GPU requests and limits
       └─ 输入输出使用对象存储或批准的共享存储
```

平台 Worker 通过集群内 ServiceAccount 访问 Kubernetes API，生产不依赖人工 kubeconfig 文件。若计算集群与控制面集群分离，则使用客户批准的短期凭据或外部身份集成，并限制目标集群、Namespace 和操作范围。

客户部署前必须确认：Kubernetes 版本及可用 Namespace/配额、GPU 型号与 Device Plugin、驱动和运行时版本、内网镜像仓库与镜像拉取策略、对象存储或 CSI/PVC、网络策略/DNS/出网限制、节点标签和污点、任务最大时长及并发配额。平台不负责安装或管理集团集群级组件。

### 9.4 Kubernetes 权限和资源边界

- 为 K8s Adapter 配置专用 ServiceAccount 和最小权限 RBAC，仅允许目标计算 Namespace 内创建/读取/删除 Job、读取 Pod 状态/日志/Events；默认不授予节点写权限或集群管理员权限。
- 计算 Pod 使用独立 Runtime ServiceAccount，默认不允许访问 Kubernetes API；对象存储凭据通过短期凭证或限定权限的 Secret 注入，不把长期凭据写入镜像或任务参数。
- 使用 Namespace ResourceQuota 和 LimitRange 控制 CPU、内存、GPU、Pod 数量及存储；平台同时设置每队列最大在途任务数，避免 Redis 队列被快速转成大量 Pod。
- CPU/GPU 节点池通过客户维护的节点标签、taint/toleration 和准入策略管理。平台工具配置只选择预先批准的资源 profile，不接受用户指定节点或任意 Kubernetes 字段。
- 平台集群页展示平台命名空间和计算 Job 的任务状态、排队时长、失败事件及配额摘要。节点级利用率/显存指标依赖客户提供的 Prometheus/GPU exporter 等只读接口，不作为提交 Job 的强依赖。

### 9.5 Job 状态、结果和清理

- Job 名称包含 task 短 ID 和 attempt 序号；标签记录 task_id、attempt_id、tool_slug、tool_version 和 workflow_run_id，避免名称泄漏用户输入。
- Job 创建请求须具备幂等键。Adapter 在 API 超时后先按幂等键或标签查询已有 Job，再决定是否重试创建，避免重复计算。
- Adapter 周期性 reconcile 数据库与 K8s 对象；Worker 重启或网络短暂中断后可继续跟踪既有 Job。
- Job 成功不代表业务任务成功：必须验证退出码、result manifest、文件 checksum 和 Artifact 登记完成后才标记 Task 成功。
- 任务日志支持运行期间查看；终态日志、Events 和失败诊断持久化到任务记录，Pod 被清理后仍可查阅。
- Job TTL 只能在结果、日志和诊断信息完成回收之后生效；失败 Job 按约定保留诊断窗口，随后由 TTL 或清理任务移除。

## 10. 数据和结果规范

即使平台裁剪，也必须保留标准 Artifact 思路。原因是工作流自动绑定、结果展示、失败排查和复现都依赖标准化结果。

最低要求：

- 每次运行保留输入快照。
- 每次运行保留参数快照。
- 每个输出文件记录 role、checksum、size 和来源任务。
- 模型输出必须包含模型名称、模型版本、endpoint、单位、适用范围和失败项。
- GROMACS 输出必须区分 trajectory、energy、structure、log、summary report。
- 任务失败不得用空文件或 0 值伪装成功结果。

## 11. 错误处理和取消

### 11.1 错误处理

| 场景 | 平台行为 |
| --- | --- |
| 输入文件格式错误 | 任务不入队或快速失败，展示可读错误 |
| 模型依赖缺失 | Worker 标记失败，展示 runtime 诊断 |
| GPU 显存不足 | 任务进入等待、失败或提示缩小 batch |
| GROMACS 中间步骤失败 | 保留 `.log`、`.mdp`、`.tpr` 和 stderr |
| 输出 manifest 缺失 | 任务失败，不生成标准 Artifact |
| 用户取消 | 同步终止底层进程或集群 job，状态变为 cancelled |

### 11.2 取消语义

取消不能只修改数据库状态，必须传递到底层执行：

- 本地 docker runner：停止对应容器或进程组。
- 本地 shell runner：终止进程组。
- SSH runner：远端 kill 进程或停止容器。
- Slurm runner：执行 `scancel`。
- Kubernetes runner：删除对应 Job/Pod。

## 12. 安全和权限

AIDD Lite 可简化权限，但不能取消安全边界。

建议保留：

- 登录认证。
- 项目级访问控制。
- 文件下载权限校验。
- 任务取消和重试权限校验。
- 任务日志脱敏。
- 模型权重和运行镜像 checksum 校验。
- 基础审计日志。

可以简化：

- 多组织租户隔离。
- 复杂管理员角色矩阵。
- 工具发布审批流。
- Agent 执行审批流。

## 13. 测试和验收

### 13.1 必测项

- 每个内置工具的 contract test。
- 每个模型的最小 smoke test。
- 每条预置工作流的端到端测试。
- 任务取消、失败、重试和日志查看。
- Artifact 下载权限。
- 单机部署启动和重启恢复。
- GPU 队列和 MD 队列并发隔离。

### 13.2 验收口径

首期验收不要求客户动态新增模型，也不要求 Agent 自动规划。验收重点应放在：

1. 固定模型和 GROMACS 工具可稳定运行。
2. 单工具和预置工作流可完成端到端任务。
3. 结果可查看、可下载、可追溯。
4. 长任务不阻塞页面和 API。
5. 部署步骤清晰，模型权重和运行环境可复现。
6. 失败任务有可读日志和可定位原因。

## 14. 实施拆分建议

### 阶段一：前端产品裁剪

- 重写路由表，只保留工作台、项目、固定工具、预置工作流、任务、结果和系统状态。
- 裁剪侧边栏、顶部入口、命令面板和面包屑，移除 Agent、研究白板、Admin 工具治理入口。
- 将工具列表改造成固定工具启动台，隐藏创建、编辑、发布、分类管理等动作。
- 将工作流页改造成模板驱动入口，保留运行状态画布，关闭任意新增节点和任意连线能力。
- 删除或隔离 conversation、agent-stream、research-boards、tool-packages publish readiness 等前端模块。
- 为被裁剪路由补 404/重定向测试，确保用户无法通过 URL 访问隐藏能力。

### 阶段二：后端平台裁剪

- 新建客户专用 repo。
- 移除 Agent、动态工具发布和复杂治理页面。
- 保留文件、任务、Artifact、工作流和基础权限。
- 固化内置工具 registry。
- 移除或关闭前端已裁剪页面对应的后端接口，避免形成隐藏管理能力。

### 阶段三：模型内嵌

- 将固定模型整理为 `model-bundles/`。
- 为每个模型补 `MODEL_PACKAGE.yaml`、`platform_run.sh`、wrapper 和 smoke test。
- 构建 runtime 镜像或 conda-pack。
- 登记权重 checksum 和运行环境摘要。

### 阶段四：调度与工作流

- 建立 `cpu_light`、`gpu_inference`、`md_heavy` 队列。
- 实现 K8s Adapter Worker，覆盖 Job 创建、幂等查询、状态 reconcile、日志采集、取消、重试和结果回收。
- 为深度学习模型和 GROMACS 分别实现 K8s Job runner，并补充 CPU/GPU 资源画像、Namespace 配额和节点标签映射。
- 编写预置工作流模板。
- 实现节点输出到下游输入的自动绑定。
- 前端接入固定工具运行、工作流模板运行、节点状态和 Artifact 下载。

### 阶段五：交付验收

- 跑单工具 smoke test。
- 跑工作流端到端测试。
- 在客户等价或真实 Kubernetes 环境验证 Job 提交、Pending 原因、GPU/CPU 调度、日志、取消、失败重试、Worker 重启恢复和 TTL 清理。
- 验证 ServiceAccount、RBAC、ResourceQuota、LimitRange、镜像拉取、对象存储/PVC 和 NetworkPolicy。
- 验证取消、失败、重试、日志和下载。
- 验证前端裁剪路由、导航和构建依赖。
- 编写客户部署说明、运维说明和验收记录。

## 15. 关键设计取舍

推荐选择“固定内置工具 + K8s Job 异步调度 + 标准 Artifact”的方案。它比完整通用平台简单，也避免把模型直接塞进 API 进程。

该方案符合 KISS 和 YAGNI：客户不需要的动态模型治理、Agent 和工具市场全部移除；但任务队列、运行隔离、结果标准化这些真正影响稳定性的机制必须保留。

最终交付边界应写清楚：这是客户专用固定模型平台，不是可由客户自行扩展模型的通用 AIDD PaaS；客户生产运行统一依赖 Kubernetes Job，平台不提供常驻模型服务和节点级调度替代品。
