# AIPhaMedX 计算任务调度系统设计文档

> 版本：V1.0（设计评审稿）｜日期：2026-10-13

> 适用范围：业务 K8s 集群 + 独立 GPU K8s 集群 + 异步临时计算任务

## 1. 文档目的与范围

本文定义 AIPhaMedX 计算任务调度系统的第一版架构、核心流程、接口边界、资源调度规则、可靠性与安全要求，为研发、算法、平台运维及客户交付团队提供统一实现依据。

本文聚焦异步计算任务：用户提交 AIDD 任务后，平台进行校验、排队、资源选择、创建计算工作负载、收集结果并更新状态。平台 Web 前后端及业务数据服务运行在业务 Kubernetes 集群；模型计算运行在独立 GPU Kubernetes 集群。

- 范围内：任务生命周期、调度、K8s Job 管理、GPU 资源请求、镜像版本、输入输出文件、失败重试、取消、监控、权限与审计。
- 范围外：具体 AIDD 算法的科学正确性、模型训练流水线、模型内部推理逻辑，以及客户底层 Kubernetes 集群的安装实施细节。

## 2. 设计原则

- 业务与计算隔离：业务集群负责交互、权限、任务元数据和调度控制；GPU 集群负责执行计算。
- 异步优先：提交任务后快速返回 task_id，计算过程通过状态查询、事件推送或 WebSocket 展示。
- 声明式执行：优先使用 Kubernetes Job 管理一次性任务，避免人工维护长期存活的临时容器。
- 镜像不可变：每次任务绑定明确的镜像 tag，生产环境进一步记录镜像 digest，禁止将 latest 作为可追溯的生产版本。
- 数据与容器生命周期分离：输入、输出和需要保留的日志/检查点必须写入持久化存储；不能只留在 Pod 临时文件系统。
- 调度与执行解耦：调度服务负责决策与状态协调，Kubernetes 负责节点级 Pod 调度和工作负载生命周期。
- 可追溯、可恢复：每个任务记录模型版本、镜像版本、参数摘要、资源申请、执行时间、重试次数和结果地址。
- 最小化首版复杂度：首版使用数据库任务表 + 持久化队列 + 调度服务 + K8s Job Controller；后续再按规模引入更复杂的批处理/工作流系统。

## 3. 总体架构

系统划分为业务控制面、任务调度面、GPU 执行面和持久化数据面。业务集群与 GPU 集群通过受控的内部 API 或消息通道通信，不要求二者处于同一个 Kubernetes 集群。

- 业务控制面（业务 K8s）：Web 前端、业务 API、身份认证、项目/任务管理、任务查询、配额管理、数据库访问。
- 任务调度面（建议部署在业务 K8s）：任务提交校验、优先级与配额、队列消费、GPU 集群路由、Job 创建与状态同步、重试与取消协调。
- GPU 执行面（独立 GPU K8s）：Kubernetes Job、计算容器、GPU Device Plugin、节点标签/污点、资源监控、镜像拉取。
- 持久化数据面：关系型数据库保存元数据；对象存储或客户共享存储保存输入、输出、日志、检查点；私有镜像仓库保存计算镜像。
- 跨集群连接：由业务侧调度服务通过经过认证的 Kubernetes API 或 GPU 集群内的执行代理提交任务。生产部署优先评估执行代理模式，以避免向业务集群暴露高权限 kubeconfig。

## 4. 核心组件与职责

| 组件 | 职责 | 首版建议 |
| --- | --- | --- |
| Web 前端 | 提交任务、展示状态/进度、下载结果 | 复用现有前端技术栈 |
| 业务 API | 鉴权、参数校验、任务记录、结果权限控制 | 现有后端框架 |
| 任务数据库 | 任务状态、参数、资源需求、版本、重试和结果索引 | PostgreSQL 或客户现有关系型数据库 |
| 消息队列 | 削峰、排队、解耦提交与执行 | RabbitMQ 等持久化队列；也可首版由数据库轮询替代，但需定义并发锁 |
| 调度服务 | 队列消费、优先级/配额检查、目标集群选择、重试策略 | 独立服务，可水平扩展 |
| GPU 执行代理（可选） | 接收已授权任务，在 GPU 集群内创建 Job 并回传状态 | 推荐用于严格网络隔离场景 |
| Kubernetes Job | 运行一次性计算容器并管理 Pod 重试 | 每个任务或任务分片一个 Job |
| 私有镜像仓库 | 保存带版本的计算镜像 | Harbor 或客户现有 Registry |
| 文件存储 | 输入、输出、日志、检查点 | S3 兼容对象存储、MinIO、NAS/NFS 或客户存储 |
| 监控与日志 | 调度指标、GPU 指标、容器日志、告警 | Prometheus/Grafana + 集中日志平台 |

## 5. 任务执行主流程

- 1）用户选择算法/模型、输入文件和参数，提交计算任务。
- 2）业务 API 完成身份与项目权限校验、参数 schema 校验、文件可访问性校验、配额检查；生成全局唯一 task_id。
- 3）数据库创建任务记录，初始状态为 QUEUED；任务消息写入持久化队列。数据库记录与队列投递需通过事务 outbox 或等价机制保证一致性，避免“有任务记录但未入队”。
- 4）调度服务领取消息，检查用户/项目配额、任务优先级、模型兼容性、GPU 类型/显存要求、集群健康和队列积压。
- 5）调度服务选择目标 GPU 集群/队列，并生成不可变的执行规格：镜像 digest、命令参数、输入输出 URI、CPU/内存/GPU 请求、超时、重试策略。
- 6）通过 GPU 执行代理或受限 Kubernetes API 创建 Job。为 Job 和 Pod 写入 task_id、project_id、model_id、model_version 等 labels/annotations。
- 7）Kubernetes 在符合资源和约束的节点上调度 Pod；节点拉取镜像，容器读取输入文件，执行计算。
- 8）计算程序将结果上传持久化存储，并写出结构化执行摘要；容器退出码表示执行成功或失败。
- 9）状态同步器监听 Job/Pod 状态，更新任务状态、开始/结束时间、资源使用和错误摘要。
- 10）前端通过查询 API、SSE 或 WebSocket 获取状态；任务成功后提供授权下载链接或受控文件访问。

## 6. 任务状态机

建议状态定义如下。状态更新必须由后端统一执行，前端不能直接修改任务状态。

| 状态 | 含义 | 允许的后续状态 |
| --- | --- | --- |
| CREATED | 已创建记录，尚未完成入队 | QUEUED、FAILED |
| QUEUED | 等待调度/资源 | DISPATCHING、CANCELLED、FAILED |
| DISPATCHING | 调度器正在创建执行工作负载 | SUBMITTED、QUEUED、FAILED、CANCELLED |
| SUBMITTED | K8s Job 已创建，等待 Pod 启动 | RUNNING、QUEUED、FAILED、CANCELLED |
| RUNNING | 计算容器正在执行 | SUCCEEDED、RETRY_WAIT、FAILED、CANCELLING |
| RETRY_WAIT | 等待按策略重试 | QUEUED、FAILED、CANCELLED |
| CANCELLING | 已请求取消，正在终止工作负载 | CANCELLED、FAILED |
| SUCCEEDED | 计算成功且结果已持久化 | 终态 |
| FAILED | 超过重试策略或不可恢复错误 | 终态 |
| CANCELLED | 任务已取消 | 终态 |

## 6.1 状态一致性规则

- 数据库是平台任务状态的权威记录；Kubernetes Job/Pod 状态是执行事实来源。状态同步器负责将执行事实映射到业务状态。
- 创建 Job 采用幂等键，例如 task_id + attempt_no；调度服务重启后可查询已有 Job，避免重复创建。
- 每次实际执行尝试分配 attempt_no，并使用独立的 Job 名称，例如 task-{task_id}-a{attempt_no}。
- SUCCEEDED 只能在确认输出文件存在、大小/校验信息有效且结果元数据写入成功后设置；仅 Pod 退出码为 0 不足以证明结果完整。
- 终态任务默认不可重新进入运行态；用户重新运行应创建新任务，或通过明确的 rerun 操作创建新的执行记录。

## 7. 调度策略

首版建议采用“先校验、后排队、按资源约束调度”的分层策略。平台业务调度器不直接替代 Kubernetes Scheduler，而是在任务级选择执行目标和资源规格，节点级落点仍由 Kubernetes 完成。

- 任务分类：按模型/算法类型划分队列，例如 docking、generation、structure_prediction、simulation、screening。
- 资源声明：每类任务定义 CPU、内存、GPU 数量、GPU 型号/显存要求、临时磁盘、最长执行时间及并发上限。
- 优先级：使用有限等级，例如 interactive、normal、batch；优先级需结合租户配额，避免单一用户长期占满资源。
- 配额：按用户/项目设置同时运行任务数、排队任务数、GPU 数量或 GPU 小时上限。
- 公平性：首版可使用每项目并发上限 + FIFO；规模扩大后再引入加权公平队列或队列配额系统。
- 节点选择：通过 nodeSelector/affinity、taints/tolerations、GPU 资源请求、节点池标签表达硬约束。
- 拥塞处理：当没有合适资源时保持 QUEUED 并记录原因，不应不断创建失败的 Job。
- 优雅降级：模型/硬件不兼容时直接拒绝或标记不可调度，不应无限重试。
- GPU 利用率与显存：K8s 的 GPU 资源请求不等于精确的显存预留；如需基于实时显存、模型驻留和队列长度进行高级调度，需额外采集 GPU 指标并开发策略，不能假设默认调度器会自动完成。

## 8. GPU 节点与资源配置

- GPU 节点安装与 GPU 型号兼容的 NVIDIA 驱动、容器运行时配置及 NVIDIA Kubernetes Device Plugin；必要时采用 NVIDIA GPU Operator 统一管理驱动/插件生命周期。
- 容器通过 limits.resources 声明 nvidia.com/gpu 数量。通常应确保 GPU request/limit 语义符合设备插件要求；不要只依赖 CPU/内存声明来调度 GPU 工作负载。
- 通过节点标签区分 GPU 型号、显存档位、用途、机房/网络区域，例如 accelerator=nvidia-h100、gpu-memory-tier=80g、workload=production。
- 使用 taints/tolerations 隔离专用 GPU 节点，避免普通业务 Pod 被调度到 GPU 节点；对关键任务配置适当的优先级与资源保障。
- 明确 GPU 独占、MIG 或共享模式。首版优先使用可预测的 GPU 分配策略；只有经过验证后再开启共享机制。
- 限制 Job 的 CPU、内存、临时存储和 GPU 使用；设置 activeDeadlineSeconds、backoffLimit、ttlSecondsAfterFinished 等生命周期参数。
- 为长任务预留足够的 ephemeral storage；大文件任务优先使用持久化存储，不应假设 Pod 本地磁盘可跨节点保留。

## 9. 镜像与模型版本管理

- 首版允许将计算代码、依赖、配置和模型权重一并打包进镜像，以简化离线/内网交付。
- 镜像采用语义化版本或不可变版本，例如 registry.example.com/aiphamedx/docking:1.3.0；生产任务同时记录 image digest，禁止依赖可变 latest 标签。
- 镜像构建流水线执行依赖锁定、漏洞扫描、模型文件校验、启动测试和最小权限检查；发布后不可覆盖相同版本标签。
- 大型权重会显著增加镜像体积、推送/拉取耗时和节点缓存占用。镜像按算法拆分，避免将所有模型权重打进一个超级镜像；可按模型大小与复用频率逐步改为权重独立存储。
- 通过 imagePullPolicy 和节点缓存策略控制镜像拉取行为。缓存只是一种性能优化，不能作为唯一的制品存储位置。
- 每个任务快照记录 model_id、model_version、image_digest、参数 schema 版本、算法配置版本和输入文件校验信息，保证结果可追溯。
- 镜像仓库需要认证、访问控制、清理策略和备份策略；含专有模型权重的镜像应视为敏感资产。

## 10. 输入、输出与临时文件管理

- 输入文件先上传到持久化文件存储，并由业务 API 记录文件 ID、URI、大小、格式、校验和、所属项目与访问权限。
- 任务启动时向容器传递文件 URI 或受控的短期访问凭据；避免把长期存储密钥直接烘焙进镜像或写入日志。
- 容器工作目录使用独立临时目录，例如 /work/{task_id}；输入可下载到本地临时盘以降低重复随机读取开销。
- 成功结果、必须保留的日志和检查点写入持久化存储。Pod 被清理后仍需保留可访问的结果文件。
- 为临时文件、失败任务产物和检查点设置保留期限；删除前遵守项目保留政策和审计要求。
- 文件访问必须做项目级鉴权；前端不应仅凭可猜测的对象存储路径直接访问他人结果。

## 11. 失败处理、重试与取消

- 区分可重试错误与不可重试错误。可重试示例：节点暂时不可用、可恢复的网络错误；不可重试示例：参数格式错误、镜像不存在、模型与 GPU 架构不兼容。
- 采用有上限的重试次数和指数退避；记录每次 attempt 的原因、开始/结束时间、Pod 退出码及错误摘要。
- 避免数据库重试与 K8s backoffLimit 双重叠加导致实际尝试次数失控。建议由平台定义任务级总重试预算，并明确 Job 内部重试策略。
- 取消任务时先将业务状态改为 CANCELLING，再删除/终止对应 Job；确认 Pod 已停止后设置 CANCELLED。
- 对长时间任务设置超时；如算法支持检查点，按任务类型配置检查点保存与恢复策略。
- 节点故障或 Pod 被驱逐时，由控制器检测并按策略重建执行；对非幂等任务，应使用 attempt 独立输出目录，避免重试覆盖已完成的结果。
- 结果写入采用临时路径加完成标记/原子提交模式，避免前端读取到不完整文件。

## 12. API 设计建议

| 接口 | 方法 | 用途 |
| --- | --- | --- |
| /api/v1/tasks | POST | 提交任务，返回 task_id 和当前状态 |
| /api/v1/tasks/{task_id} | GET | 查询状态、进度、资源信息和错误摘要 |
| /api/v1/tasks | GET | 按项目、用户、状态、模型、时间分页查询 |
| /api/v1/tasks/{task_id}/cancel | POST | 请求取消任务 |
| /api/v1/tasks/{task_id}/logs | GET | 获取授权范围内的日志摘要或日志地址 |
| /api/v1/tasks/{task_id}/results | GET | 获取结果清单及受控下载地址 |
| /api/v1/models | GET | 查询可用模型、版本和资源要求 |

## 12.1 任务提交请求示例

示例仅用于说明字段边界，具体字段应由各算法的参数 schema 定义。

- project_id：所属项目。
- model_id / model_version：模型标识和版本。
- input_files：已上传文件的 ID 或受控 URI。
- parameters：算法参数，必须经过模型专属 schema 校验。
- priority：有限优先级枚举。
- resource_profile：可选资源档位；用户不能直接提交任意 Kubernetes YAML。
- idempotency_key：客户端重试提交时避免重复创建任务。

## 12.2 响应示例

成功响应可返回：{"task_id":"task_01...","status":"QUEUED","created_at":"...","status_url":"/api/v1/tasks/task_01..."}。真实 API 应统一错误码、分页格式、时间格式与请求追踪 ID。

## 13. 数据模型建议

| 实体 | 关键字段 | 说明 |
| --- | --- | --- |
| Task | task_id, project_id, user_id, model_id, model_version, status, priority, created_at, started_at, finished_at | 任务主记录 |
| TaskAttempt | attempt_id, task_id, attempt_no, job_name, pod_name, status, exit_code, error_code, started_at, finished_at | 每次执行尝试 |
| TaskResource | task_id, cpu_request, memory_request, gpu_type, gpu_count, gpu_memory_requirement, runtime_limit | 资源需求快照 |
| TaskArtifact | artifact_id, task_id, artifact_type, uri, size, checksum, created_at | 输入、输出、日志和检查点索引 |
| ModelRelease | model_id, version, image_digest, default_resources, parameter_schema_version, enabled | 可部署模型版本 |
| TaskEvent | event_id, task_id, event_type, timestamp, payload | 审计和状态事件 |

## 14. 安全与租户隔离

- 业务服务使用服务身份调用 GPU 执行面；不将管理员级 kubeconfig 放入前端或普通业务容器。
- 如需跨集群直接访问 Kubernetes API，使用专用 ServiceAccount、最小 RBAC 权限、短期凭据和网络白名单；只允许创建/查询限定 namespace 内的指定工作负载类型。
- 更推荐在 GPU 集群部署执行代理，由业务调度服务提交经过签名/认证的任务规格，代理负责在本集群创建 Job，减少跨集群高权限凭据暴露。
- 禁止用户直接指定任意镜像、命令、挂载路径、hostPath、特权模式或任意环境变量；任务规格由模型注册信息与经过校验的参数生成。
- Pod 使用非 root 用户、只读根文件系统（可行时）、删除 Linux capabilities、seccomp、资源限制和网络策略。
- 模型镜像与权重属于专有资产，镜像仓库应按客户/租户设置访问权限；日志中不得记录长期密钥或敏感输入内容。
- 任务查询、取消、下载结果都必须执行用户、项目与租户权限校验；所有管理员操作应写入审计日志。

## 15. 可观测性与告警

| 指标/事件 | 用途 | 建议告警 |
| --- | --- | --- |
| 排队任务数、最老任务等待时间 | 判断资源拥塞与调度停滞 | 超过业务 SLA 阈值 |
| 任务成功率、失败率、重试率 | 评估执行稳定性 | 按模型/版本持续异常 |
| Job 创建失败数、状态同步延迟 | 定位集群 API 或控制器问题 | 错误率或同步延迟持续升高 |
| GPU 利用率、显存、温度、XID/设备异常 | 观察 GPU 健康与利用效率 | 设备异常、温度或显存压力异常 |
| 镜像拉取耗时/失败率 | 识别镜像体积或 Registry 问题 | 拉取失败或启动延迟超阈值 |
| 输入下载/结果上传耗时 | 定位存储瓶颈 | 持续超时或上传失败 |
| 每任务 GPU 时间、CPU/内存、存储用量 | 成本归集与配额管理 | 超过项目预算/配额 |
| 调度队列消费延迟、死信数 | 发现消息堆积与异常任务 | 队列持续积压 |

## 16. 高可用与容量规划

- 业务调度服务保持无状态，可多副本部署；通过数据库锁、队列消费者竞争或租约机制确保同一执行尝试只被一个调度者处理。
- 任务数据库和消息队列应纳入备份、恢复和容量监控；任务状态不可只存在内存中。
- GPU 集群不可用时，任务留在队列中并向用户展示等待/受阻原因；恢复后继续调度，不应在业务 API 中长时间同步等待。
- 容量规划需要测量模型镜像大小、节点本地缓存容量、平均启动时间、模型加载时间、平均 GPU 执行时长、失败率和任务峰值。
- 按模型分层统计队列等待时间和执行时长；资源需求应来自基准测试，不仅依赖开发人员估算。
- 如需跨 GPU 集群/机房调度，首版可由平台按模型兼容性和可用容量选择目标集群；跨区域数据传输、合规与存储访问需单独评估。

## 17. 首版实施范围与迭代路线

| 阶段 | 交付内容 | 验收重点 |
| --- | --- | --- |
| 阶段 1：最小可用调度 | 任务 API、数据库、持久化队列、调度服务、GPU K8s Job、状态同步、输入输出存储 | 能提交、排队、执行、查看状态、获取结果 |
| 阶段 2：可靠性 | 幂等创建、重试/取消、超时、日志归集、结果校验、失败分类 | 异常任务可恢复、不会无限重试或产生重复结果 |
| 阶段 3：资源治理 | 模型资源档案、GPU 节点标签、项目配额、优先级、GPU 指标 | 不兼容任务可识别，队列和资源使用可观测 |
| 阶段 4：生产强化 | 镜像扫描、RBAC、审计、备份恢复、SLA 告警、成本归集 | 满足客户安全、运维与交付要求 |
| 阶段 5：高级调度（按需） | 加权公平队列、跨集群调度、缓存预热、批量任务工作流、检查点恢复 | 由真实吞吐、等待时间和资源利用率数据驱动优化 |

## 18. 关键验收标准

- 任务提交 API 能在合理时间内返回 task_id，不等待实际计算完成。
- 任务状态在排队、调度、运行、成功、失败、取消等阶段可查询，并具有可追溯的时间戳。
- 每个执行尝试使用确定的镜像版本/digest 和模型版本。
- GPU 任务只会被调度到符合 GPU 类型、数量及节点约束的节点。
- Job 失败、节点暂时不可用或调度服务重启后，不会丢失已提交任务。
- 重复提交请求可通过幂等键避免意外生成重复任务。
- 任务取消会终止对应计算工作负载，并最终反映到业务状态。
- 任务结果写入持久化存储后才标记 SUCCEEDED；Pod 清理后结果仍可访问。
- 普通用户不能读取其他项目的任务、日志或结果，不能通过请求参数执行任意容器命令。
- 可按任务/模型/项目查询失败率、排队时长、执行时长、GPU 使用和镜像拉取耗时。

## 19. 需要在详细设计阶段确认的事项

- 客户是否允许业务集群直接访问 GPU 集群 Kubernetes API，还是必须通过 GPU 集群内执行代理。
- GPU 型号、单机 GPU 数量、显存、驱动/CUDA 兼容矩阵及是否允许 MIG/共享 GPU。
- 各模型权重体积、镜像大小、启动频率、预计任务并发量和任务时长分布。
- 客户提供的对象存储/NAS、镜像仓库、数据库、消息队列和日志平台是否已有标准服务。
- 任务输入输出的保留期限、数据分级、审计要求和是否允许跨机房传输。
- 哪些算法可安全重试、哪些算法支持检查点，以及每类任务的默认资源与超时。
- 平台需要支持的优先级、项目配额、用户限额和计算成本计量规则。

## 20. 与现有 DEMO 合并时的审查矩阵

### 20.1 审查口径与总体结论

本节按 2026-10-13 当前仓库工作区审查，包含审查时已存在的未提交改动。结论基于代码、测试、部署样例和文档；有适配器或测试不等于已在目标客户的双集群环境完成部署、联调和生产验收。

状态说明：**基本具备**表示仓库中已有可复用的主要闭环；**部分具备**表示已有实现或测试，但与本蓝图的领域模型、跨集群闭环或生产验收仍有差距；**未见证据**表示本次审查未在仓库找到实现/部署证据，不代表技术上不可实现。

总体判断：当前 `cpumodel_sciminer` 不是只有静态页面的空壳 DEMO。它已有真实的任务 API、Celery/Redis 异步执行、工具版本与资源档位、文件/Artifact 存储，以及可选 Kubernetes Job 执行适配器；同时还包含工作流、工具管理等更广的平台能力。但其现有主干仍是“Task + Worker/Executor”的通用工具执行平台，和本设计稿提出的“任务调度控制面 + GPU 集群 Job 执行面 + 显式 TaskAttempt/状态协调”的目标模型并不完全一致。建议保留已验证的业务与执行能力，在其后重构调度领域边界，不建议把当前实现直接视为蓝图已验收，也不建议仅因 DEMO 名称而推倒重写。

另需区分：`AIPhaMedX_Clickable_Prototype.html` 明确包含本地模拟交互；它只能证明交互草图，不能作为真实任务执行证据。下表以应用代码、测试和部署样例为准。

### 20.2 对照矩阵

| 审查域 | 蓝图目标 | 当前 DEMO 证据与差距 | 判定 | 合并/重构建议 |
| --- | --- | --- | --- | --- |
| 任务提交与查询 | 校验权限、参数、输入并快速返回任务 ID；查询状态、日志、结果 | 已有创建、列表、详情、取消、重试、日志 API 和任务页面；使用项目/工具任务语义。任务状态仍主要是 `PENDING/RUNNING/SUCCESS/FAILURE/CANCELED`，没有蓝图完整的 `QUEUED/DISPATCHING/SUBMITTED/RETRY_WAIT/CANCELLING` 展示闭环。证据：`backend/app/api/v1/tasks.py`、`backend/app/tasks/service.py`、`frontend/src/views/tasks/` | 部分具备 | 保留现有鉴权、参数/Artifact 输入校验和 API 门面；新调度内核用明确状态机，并通过兼容映射维持旧 API 一段迁移期。 |
| 队列与提交可靠性 | 数据库任务记录和持久队列可靠衔接；建议 outbox/等价机制 | 已有 Celery 队列管理、Redis Broker、优先级与等待时间加权；生产 Compose 配有 Celery Worker。任务持久化与 Celery 投递目前分步提交，未见事务 outbox 或等价的原子投递机制；任务创建 schema 也未见客户端幂等键。证据：`backend/app/tasks/queue_manager.py`、`backend/app/tasks/service.py`、`backend/app/schemas/tasks.py`、`deploy/compose/docker-compose.prod.yml` | 部分具备 | 先补任务创建幂等键及 outbox/可恢复 dispatch 状态；在双集群网络和队列方案确定前，不要把 Redis 队列直接等同于目标调度服务。 |
| 状态与执行尝试 | Task 与每次 Attempt 分离，状态事件可追溯、可恢复 | 有 attempt ID、任务状态机和面向部分工具包执行的 `ExecutionRecord`（含 attempt 幂等键、请求快照、外部执行 ID）；旧 `Task` 仍承载聚合状态，执行记录也不是所有任务统一必有，尚未看到完整 TaskEvent 状态事件模型。证据：`backend/app/models/tasks.py`、`backend/app/models/executions.py`、`backend/app/execution/records.py`、`backend/app/tasks/state_machine.py` | 部分具备 | 将蓝图的 `Task/TaskAttempt/TaskEvent/TaskResource/TaskArtifact` 作为新领域模型目标；先定义旧任务、工作流运行和新执行尝试之间的映射，不要继续把调度字段塞入 `extra_data`。 |
| 资源准入与队列路由 | 按资源档案、优先级、配额及兼容性选择目标 GPU 集群/队列 | 已有资源档案快照、Worker capability、容量准入/租约、用户/项目资源限额和队列路由；当前主要是选择可用 Worker/队列，不是多 GPU 集群的健康、容量与模型兼容路由，部分准入路径还以观测元数据形式记录。证据：`backend/app/tasks/resource_profile.py`、`backend/app/tasks/resource_admission.py`、`backend/app/tasks/worker_capability_registry.py`、`backend/app/tasks/resource_quota.py`、`backend/app/tasks/service.py` | 部分具备 | 复用资源档案与配额概念；抽出独立 Scheduler/Cluster Provider 接口，明确“排队等待”与“不可调度拒绝”的语义，再接入 GPU 集群路由。 |
| Kubernetes Job 执行 | 由 GPU 执行面创建 Job、同步状态/日志、取消并回收结果 | 已有 Kubernetes Job manifest 构造、REST transport、执行 adapter、日志/状态/取消/Artifact 收集接口及相关测试；另有执行 Worker、RBAC 和镜像模板样例。部署样例不是默认启用的完整双集群交付，当前配置按单个集群 alias/namespace 构造运行时；仓库测试不能证明目标 GPU 集群已真实联通。证据：`backend/app/execution/adapters/kubernetes.py`、`backend/app/execution/adapters/kubernetes_manifest.py`、`backend/app/execution/transports/kubernetes_http.py`、`test/test_kubernetes_http_transport.py`、`deploy/kubernetes/execution-worker.example.yaml`、`deploy/kubernetes/README.md` | 部分具备 | 把现有 adapter 作为可复用执行器，而不是新的调度核心；优先做独立 GPU 集群的端到端部署验证、凭据轮换、断连恢复和 Job 生命周期验收。 |
| GPU 约束 | GPU 数量、型号/显存、节点标签/污点和 CPU/内存/超时约束准确落到 Job | 资源档案和 Worker capability 可表达 GPU 数量/显存需求；Job manifest 可写入 `nvidia.com/gpu`、CPU/内存、超时、TTL，已有 GPU 探测/分配相关代码。Job manifest 当前未见 GPU 型号对应的 `nodeSelector/affinity`、`tolerations` 或显存预留机制；Worker 的 GPU 数量声明不等于目标节点真实可用性。证据：`backend/app/tasks/resource_profile.py`、`backend/app/tasks/resource_admission.py`、`backend/app/execution/adapters/kubernetes_manifest.py`、`backend/app/gpu/allocator.py` | 部分具备 | 将硬约束作为经平台验证的 `ResourceProfile`/Cluster capability，而不是用户可提交任意 K8s 字段；补 GPU 型号、节点池、MIG/共享策略的目标环境验收。 |
| 镜像与模型版本 | 每次尝试固定模型/镜像版本和 digest，生产镜像可审计 | Tool Package/ToolVersion 提供版本化工具制品；K8s Job 要求镜像使用 `sha256` digest，支持镜像拉取 Secret。仍需确认模型版本与工具版本的正式映射、构建/漏洞扫描/签名/制品留存流水线；未见生产级镜像发布流水线证据。证据：`backend/app/tools/version_manager.py`、`backend/app/execution/adapters/kubernetes_manifest.py`、`deploy/kubernetes/model-image-template/` | 部分具备 | 复用工具包版本管理作为制品来源，补齐模型发布元数据与不可变镜像发布门禁；运行快照固定版本、digest、参数 schema 版本及输入校验和。 |
| 输入、输出与持久化 | 输入可访问；结果先持久化并校验后再成功；Pod 清理后仍可取回 | 已有本地/MinIO 存储、Artifact/Execution Artifact、K8s Job 对象存储输出及结果收集；Artifact 记录可保存摘要信息。仍需端到端验证结果完整性、成功状态与上传提交的原子边界、失败产物清理和保留策略。证据：`backend/app/storage/`、`backend/app/execution/transports/kubernetes_artifacts.py`、`backend/app/services/execution_artifacts.py`、`backend/app/services/execution_results.py` | 部分具备 | 统一任务输入/输出 Artifact 契约与访问策略；补完成标记/原子发布、校验失败分类、TTL/保留策略和 Pod 清理后的恢复测试。 |
| 失败、重试、超时与取消 | 有限且可解释的任务级重试；取消确认工作负载停止 | 有最大重试次数、用户重试、资源等待重试/恢复、取消流程；K8s Job 设置 `backoffLimit=0` 和 `activeDeadlineSeconds`，由平台层控制重试。尚需统一不同执行器的失败分类、退避/总重试预算和尝试记录；检查点恢复未见通用实现证据。证据：`backend/app/tasks/state_machine.py`、`backend/app/tasks/cancellation.py`、`backend/app/tasks/recovery.py`、`backend/app/execution/adapters/kubernetes_manifest.py` | 部分具备 | 让 Scheduler/Attempt 层成为唯一重试预算与取消状态的权威来源；明确定义 K8s Job 内部重试为 0 或受控值，避免双重重试。 |
| 权限、隔离与审计 | 项目/租户鉴权、最小 RBAC、受控镜像/命令、敏感信息不泄露 | 任务读取和操作有项目角色检查；K8s 有 namespace 级 RBAC、执行 Worker ServiceAccount 和模型 Job 使用的独立 ServiceAccount 样例。目标 Job 的 Pod 安全上下文、网络策略、租户级 Registry 策略及所有管理员调度操作审计尚未形成可验证的统一交付闭环。证据：`backend/app/services/task_access.py`、`backend/app/api/v1/artifacts.py`、`deploy/kubernetes/execution-rbac.yaml`、`backend/app/execution/adapters/kubernetes_manifest.py` | 部分具备 | 保留现有项目权限与制品访问控制；将 Job 安全上下文、Secret 引用、可执行字段白名单、审计事件纳入执行规格和部署验收。 |
| 可观测性与告警 | 任务/队列/Job/GPU/存储/成本指标可按项目和模型查询、告警 | 已有 Prometheus 指标、任务时长/活跃任务指标、GPU 监测/告警与 Celery 队列状态查询；未见蓝图要求的跨集群 Job 创建延迟、最老排队时长、镜像拉取耗时、每任务 GPU 成本等完整指标和生产告警部署证据。证据：`backend/app/monitoring/prometheus_metrics.py`、`backend/app/monitoring/metrics_collector.py`、`backend/app/tasks/queue_manager.py`、`backend/app/gpu/monitor.py` | 部分具备 | 先统一 Task/Attempt/Cluster 标签与事件时间戳，再补队列等待、调度耗时、Job 生命周期、上传耗时及资源成本指标；避免只看 Worker 健康度。 |
| 高可用与容量规划 | 多副本调度、故障恢复、持久队列/数据库及基准驱动容量规划 | 有任务/执行记录持久化、恢复与对账逻辑、worker capability 心跳/租约；现有 K8s Worker 样例为单副本，Compose 更适合单机/演示形态，未见双集群 HA、备份恢复演练或容量基准报告。证据：`backend/app/execution/records.py`、`backend/app/tasks/recovery.py`、`deploy/kubernetes/execution-worker.example.yaml`、`deploy/compose/docker-compose.prod.yml` | 部分具备 | 将 HA、备份、重启/断连恢复作为上线门槛；先取得真实模型启动/执行/镜像拉取数据，再制定容量和 SLA，不提前建设复杂公平调度。 |
| API 与前端结果体验 | 前端提交、进度、状态、日志和受控结果下载 | 正式 Vue 应用有任务、工作流运行页面和对应 API；任务详情/Artifact 接口已提供实际业务能力。可点击 HTML 原型中的项目、通知、文件上传和运行记录明确是模拟行为，不能与正式应用功能混算。证据：`frontend/src/router/index.ts`、`frontend/src/views/tasks/`、`frontend/src/api/workflows.ts`、`docs/dev/AIPhaMedX_Clickable_Prototype.html` | 部分具备 | 从正式 Vue 应用迁移产品体验；把原型仅作为交互参考，验收须走真实 API、真实 K8s Job、授权下载和运行记录。 |

### 20.3 合并建议与重构顺序

1. **保留业务资产**：项目/用户权限、任务提交与查询 API、工具/版本管理、输入校验、Artifact/MinIO、任务列表/详情以及工作流能力。这些属于平台业务面，不应因调度重构而整体重写。
2. **重构调度核心**：新增清晰的任务执行领域边界，统一 `Task → TaskAttempt → Execution` 状态与事件；把资源快照、幂等、outbox/dispatch、集群路由、重试预算和取消协调从旧 `Task.extra_data`/Worker 分支逐步迁出。
3. **以适配器迁移执行器**：保留 Kubernetes/SSH/本地等执行器作为 Adapter；让新调度核心面向统一 Execution Contract，不让 Celery、旧 Task 状态或特定执行器成为领域模型本身。分阶段双写/映射并做回归，避免一次性切换全部工具与工作流。
4. **先验证闭环，再谈生产化**：优先完成独立 GPU 集群上的提交—排队—Job 创建—状态/日志回传—结果持久化—取消/重启恢复的端到端验收；之后再补多集群路由、GPU 节点约束、镜像供应链、HA、告警与成本治理。

推荐的近期设计产物是“旧任务/工作流与新执行模型映射表 + 新状态机/事件模型 + 单 GPU 集群最小端到端验收场景”。在这三项确认前，不宜先按蓝图直接重写全部任务 API 或引入高级公平调度。
