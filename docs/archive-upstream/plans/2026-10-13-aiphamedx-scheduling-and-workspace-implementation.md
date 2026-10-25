# AIPhaMedX 调度重构与研究工作台实施计划

> 版本：V1.0 实施计划｜日期：2026-10-13
> 关联设计：`docs/plans/2026-10-13-cpumodel-scheduling-and-workspace-redesign.md`
> 目标：将现有 `cpumodel_sciminer` 渐进迁移为 AIPhaMedX 计算调度平台与研究工作台

## 1. 实施基线

### 1.1 排期假设

以下排期按一个小型跨职能小组估算：

- 后端/调度：2 人。
- 前端/交互：2 人。
- 基础设施/测试：1 人兼职支持。
- 产品/算法代表：每周参与验收和模型运行场景确认。

若实际只有 1 名后端或 1 名前端，预计总周期至少增加 40%–60%；不建议在没有 GPU 集群测试环境的情况下提前压缩阶段 3 的端到端验收时间。

### 1.2 实施原则

1. **先建立可回滚的兼容层，再迁移主路径**：旧 `Task`、旧路由、旧 `sciminer` 资源和旧协议读取能力在稳定版本周期内保留。
2. **一次只切换一个真实执行类型**：先选择一个 `k8s_job` GPU 工具作为试点，不同时迁移所有工具和工作流节点。
3. **前后端契约先行**：前端不直接读取 `extra_data`，后端不为前端临时拼接新的状态字段。
4. **所有生产切换由 Feature Flag 控制**：可按用户、项目、工具版本和环境逐步放量。
5. **验收证据优先于代码完成**：每个里程碑必须有测试、指标、运行记录或部署演练证据，不能只以“代码已合并”作为完成标准。

### 1.3 目标发布版本

| 版本 | 目标 | 说明 |
| --- | --- | --- |
| `AIPhaMedX 0.1` | 兼容基础和品牌基础 | 新品牌 UI、命名注册表、Run/Attempt 双写、旧接口继续可用 |
| `AIPhaMedX 0.2` | 新运行中心 | `/runs` 查询、运行详情、状态时间线和统一 Artifact 体验 |
| `AIPhaMedX 0.3` | 单 GPU 集群闭环 | 新 Scheduler/Reconciler 驱动一个 `k8s_job` 工具完成真实运行 |
| `AIPhaMedX 0.4` | 生产强化 | HA、告警、审计、镜像/Secret 安全和故障恢复演练 |
| `AIPhaMedX 1.0` | 默认新路径 | 新品牌和新运行模型成为默认，旧路径进入只读兼容期 |

## 2. 总体里程碑

基准开始日期为 **2026-10-14**。日期是实施基准，不代表必须在没有验收证据时强行上线。

| 里程碑 | 日期 | 主题 | 退出条件 |
| --- | --- | --- | --- |
| M0 | 2026-10-14 – 2026-10-20 | 基线、命名盘点与冻结 | 现状指标、兼容矩阵、决策记录和试点工具确定 |
| M1 | 2026-10-21 – 2026-11-03 | 领域模型与数据迁移底座 | Run/Attempt/Event/Resource/Outbox 模型和旧 Task 映射通过测试 |
| M2 | 2026-11-04 – 2026-11-17 | 双写与统一执行契约 | 新运行可创建、幂等、入 Outbox，并能投影到旧 Task |
| M3 | 2026-11-18 – 2026-12-01 | Scheduler/Reconciler | 新调度控制面在 Direct/Celery 环境可恢复运行 |
| M4 | 2026-12-02 – 2026-12-15 | AIPhaMedX 前端 Shell 与工作台 | 新品牌视觉和工作台首页灰度可用 |
| M5 | 2026-12-16 – 2026-12-29 | 运行中心与运行详情 | `/runs`、运行时间线、Attempt、日志和 Artifact 可用 |
| M6 | 2026-12-30 – 2027-01-12 | GPU K8s 真实闭环 | 一个 GPU `k8s_job` 工具完成全链路验收 |
| M7 | 2027-01-13 – 2027-01-26 | 品牌运行时命名与生产强化 | 新资源使用 `aiphamedx`，旧资源可观测可回滚，HA/告警/安全通过 |
| M8 | 2027-01-27 – 2027-02-02 | 灰度发布与旧路径退役决策 | 达到发布门槛，决定扩大灰度、暂停或回滚 |

## 3. M0：基线、命名盘点与冻结

### 3.1 目标

在开始数据库和前端大改之前，冻结当前可用行为，确认 AIPhaMedX 新路径的边界。

### 3.2 工作包

**M0-A：运行基线**

- 记录 Direct、Celery/Redis、Kubernetes Adapter 三种执行模式的现状行为。
- 记录任务创建、入队、开始、完成、结果上传、取消确认的耗时。
- 记录当前任务状态、工作流运行状态、执行记录和 Artifact 的映射关系。
- 选择一个有固定镜像 digest、可稳定运行、输入输出明确的 GPU `k8s_job` 工具作为试点。

**M0-B：命名注册表**

- 建立 `AIPhaMedX / aiphamedx / CPUModel / cpumodel / sciminer / scitool` 的使用位置清单。
- 按“可直接改名、需双读兼容、必须保持不变、暂不迁移”分类。
- 识别所有外部消费者：镜像仓库、Kubernetes namespace、Redis key、对象存储路径、Tool Package 协议、前端 localStorage、CI/CD 和部署文档。
- 记录仓库目录改名的前置依赖，但不在 M0 执行 Git 远程或目录移动。

**M0-C：契约冻结**

- 冻结旧任务 API 的字段和状态兼容规则。
- 冻结新 `RunSummary`、`RunDetail`、`RunAttempt` 和 `RunEvent` 查询契约草案。
- 冻结新状态机和失败分类表。
- 写出 ADR：为什么保留 `app` Python 包、为什么旧协议不做原地改名、为什么先迁移一个 `k8s_job` 工具。

### 3.3 交付物

- 命名注册表和兼容矩阵。
- 试点工具说明和端到端测试数据集。
- 现状运行基线报告。
- 新旧状态、实体和 API 映射表。
- 失败分类与回滚触发条件。

### 3.4 里程碑门槛

- 能从数据库、队列、执行记录和 K8s Job 四处定位同一个任务。
- 至少完成一次现有试点工具的成功和失败运行留档。
- 产品、后端、前端和基础设施负责人确认新旧命名边界。

## 4. M1：领域模型与数据迁移底座

### 4.1 目标

建立新运行模型，但不切换用户默认执行路径。

### 4.2 后端任务

- 新增 `Run`：用户可见的一次运行，保存项目、来源类型、状态、优先级和兼容旧任务 ID。
- 新增 `RunAttempt`：保存 Attempt 编号、执行器类型、外部句柄、状态、退出码、错误分类和时间。
- 新增 `RunResource`：保存不可变资源请求和调度快照。
- 新增 `RunEvent`：保存状态变化、调度决策、取消、重试和结果提交事件。
- 新增 `DispatchOutbox`：保存待投递的调度消息、投递次数、下一次重试时间和死信原因。
- 增加必要的唯一索引：`project_id + idempotency_key`、`run_id + attempt_no`、`run_id + event_sequence`。
- 以新的 Alembic migration 建表，迁移必须支持空数据库和已有数据库两种路径。

### 4.3 兼容策略

- 现有 `Task` 表继续保留，不修改历史状态含义。
- 旧任务创建路径通过一个投影模块生成 `Run`，而不是让 API 层同时维护两套业务逻辑。
- 历史 Task 没有对应 Run 时，查询层生成只读兼容视图，不批量伪造执行事件。
- `ExecutionRecord` 通过 `legacy_task_id`、`run_id` 或兼容关联字段接入新 Attempt；不复制敏感请求参数。

### 4.4 验收

- 新模型迁移可重复执行，升级和回滚行为有测试。
- 同一个幂等键重复提交只产生一个 Run。
- 同一个 `run_id + attempt_no` 重复消费不会创建第二个 Attempt。
- 旧任务列表、详情、日志和结果读取不回归。

## 5. M2：双写与统一执行契约

### 5.1 目标

让新运行成为新的业务事实来源，同时保留旧 Task API 的投影和兼容响应。

### 5.2 工作包

**M2-A：运行创建模块**

- 从 `backend/app/tasks/service.py` 抽出运行意图准备、输入绑定、资源快照和运行创建模块。
- 任务准备成功后在一个数据库事务中写入 Run、RunResource、输入 Artifact 快照和 Outbox。
- 对外支持 `Idempotency-Key` 请求头和请求体字段，优先使用请求头。
- 幂等键必须绑定用户和项目，跨项目复用同一个键不能返回其他项目的运行。

**M2-B：统一执行契约**

- 复用 `backend/app/execution` 的 Gateway/Adapter seam。
- 将 Kubernetes、SSH、Direct 适配为同一组 submit/inspect/reconcile/cancel/logs/result 生命周期。
- Direct 模式只用于开发和测试，不绕过 RunAttempt 和 RunEvent。
- 外部执行句柄、Job 名称和对象存储输出前缀必须从稳定的 Run/Attempt 标识生成。

**M2-C：旧模型投影**

- 新 Run 状态投影为旧 Task 的 `PENDING/RUNNING/SUCCESS/FAILURE/CANCELED`。
- 旧任务详情增加兼容字段：`run_id`、`attempt_id`、新状态和等待原因。
- 不让新前端读取旧 Task 的 `extra_data` 作为状态协议。

### 5.3 验收

- 数据库提交成功但进程在投递前退出时，Outbox 能重新投递。
- Celery 消费失败、重复消费和消息延迟不造成重复 Attempt。
- 旧任务和新 Run 页面显示的状态最终一致。
- 现有工作流运行仍可创建节点任务并获得兼容投影。

## 6. M3：Scheduler 与 Reconciler

### 6.1 目标

把调度决策和外部执行事实从 API 请求、Celery Worker 和具体 Executor 中抽离。

### 6.2 Scheduler 工作包

- 新增资源准入接口：输入 RunResource 和 ClusterCapability，输出 `accepted/waiting/rejected`。
- 复用现有 Worker capability、资源配额和租约，统一转换为 ClusterCapability。
- 调度决策写入 RunEvent，包含队列、集群、资源档案、原因和决策版本。
- 资源不足保持 `QUEUED`，不创建失败 Job。
- 模型/镜像/GPU 架构不兼容进入明确拒绝状态，不做无限重试。
- 每个 Attempt 使用数据库租约或等价机制，保证同一尝试只有一个调度者。

### 6.3 Reconciler 工作包

- 扫描 `DISPATCHING/SUBMITTED/RUNNING/CANCELLING` 的 RunAttempt。
- 根据外部执行状态映射新状态和失败分类。
- K8s Job 创建返回 409 时按稳定幂等名称读取已有 Job。
- 结果收集后执行存在性、大小、checksum、schema 和权限校验。
- 取消先写 `CANCELLING`，确认 Job/Pod 停止后写 `CANCELLED`。
- 处理 Worker 重启、Redis 重启、K8s API 暂时不可用和外部 Job 已删除等情况。

### 6.4 运行模式

| 模式 | 用途 | 允许范围 |
| --- | --- | --- |
| Direct | 单元/集成测试和本地开发 | 不作为生产执行模式 |
| Celery + Redis | 第一阶段持久化消息传输 | 可作为生产过渡方案，状态以数据库为准 |
| GPU K8s Job | 目标生产执行面 | M6 之后对试点工具启用 |

### 6.5 验收

- 调度服务重启后未完成运行自动恢复，不重复创建外部 Job。
- GPU 集群不可用时任务保持等待并展示原因。
- 同一个 Attempt 的重试、取消和结果回传不会相互覆盖。
- K8s Job 内部重试和平台级重试总预算可证明不叠加失控。

## 7. M4：AIPhaMedX 前端 Shell 与工作台

### 7.1 目标

先在不依赖新后端 Run API 的情况下，完成品牌和核心研究工作台的视觉升级。

### 7.2 实施顺序

1. 更新 `frontend/index.html`、路由标题、国际化品牌文案和登录/错误页面为 AIPhaMedX。
2. 建立 Design Tokens：深蓝侧栏、青绿色主色、页面/卡片/输入三层 surface、状态色、间距和圆角。
3. 重做 `AppShell.vue`：工作区切换、分组导航、顶部搜索/通知/用户区、移动端抽屉。
4. 重做 `workspace/index.vue`：欢迎区、运行状态带、进行中运行、项目快捷入口、最近 Artifact 和资源状态。
5. 增加项目上下文导航，统一项目总览、研究、工作流、运行、数据、谱系和设置。
6. 建立 `RunStatusModel`，先把旧 Task 和 WorkflowRun 映射为统一展示模型。

### 7.3 视觉验收

- 桌面端、收起侧栏、平板和移动端布局稳定。
- 新页面不再出现 `CPUModel` 作为用户可见品牌。
- 原型中的“模拟/未连接”提示规则被保留，真实页面不能伪造运行状态。
- 视觉回归基线覆盖 App Shell、工作台、项目总览、工具目录和任务列表。

## 8. M5：运行中心与运行详情

### 8.1 目标

让用户通过一个统一入口理解独立工具运行、工作流运行、排队、执行、失败和结果。

### 8.2 后端接口

- `GET /api/v1/runs`：按项目、状态、运行类型、工具/模型和时间分页查询。
- `GET /api/v1/runs/{run_id}`：返回 Summary、Attempt、Event、资源、输入、输出、质量摘要和权限。
- `GET /api/v1/runs/{run_id}/events`：增量读取状态事件。
- `GET /api/v1/runs/{run_id}/logs`：按 Attempt 和 cursor 读取授权日志。
- `POST /api/v1/runs/{run_id}/cancel`：请求取消并返回 `CANCELLING`。
- `POST /api/v1/runs/{run_id}/rerun`：创建新的 Run，不复用旧 Attempt。
- `/api/v1/tasks` 和 `/api/v1/workflows/runs` 保留兼容响应和跳转字段。

### 8.3 前端工作包

- 新增 `/runs` 路由和统一运行列表。
- 新增 `/runs/:runId` 路由和运行详情。
- 实现运行状态带、过滤器、等待原因、失败分类、Attempt 时间线和资源摘要。
- 实现日志、Artifact、配置快照和质量验证摘要的分栏/折叠展示。
- 旧 `/tasks` 和 `/tasks/:id` 跳转到兼容运行详情，但在稳定期保留旧页面入口。

### 8.4 验收

- 用户可以从项目、工具和工作流进入同一运行详情。
- 运行详情展示真实状态事件和 Attempt，不依赖本地模拟数据。
- 日志、结果和 Artifact 遵守项目权限。
- 取消、重试和 rerun 的动作语义在 UI 中明确区分。

## 9. M6：单 GPU 集群端到端闭环

### 9.1 目标

只选择一个固定 digest 的 GPU `k8s_job` 工具，验证蓝图的最小生产闭环。

### 9.2 环境准备

- 准备业务集群、GPU 集群、Registry、MinIO/对象存储、数据库和 Redis 的连接清单。
- 创建最小权限 ServiceAccount、namespace、Role/RoleBinding、Secret 和网络白名单。
- 确认 GPU 型号、显存、驱动/CUDA、Device Plugin、节点标签和污点。
- 为试点工具准备固定 digest 镜像、输入样本、预期输出 schema 和校验和。
- 配置 `aiphamedx` 新资源命名仅用于新建试点资源；旧 `sciminer` 资源继续可查询。

### 9.3 端到端场景

1. 用户在项目中上传输入 Artifact。
2. 选择试点工具版本和资源档案，提交带幂等键的运行。
3. API 快速返回 `run_id`，Outbox 可靠投递。
4. Scheduler 选择 GPU 集群和队列，创建唯一 Attempt。
5. Adapter 创建 Job，写入 Run/Attempt/Project/Tool labels。
6. K8s 在符合 GPU 资源的节点启动容器并写入日志。
7. 结果上传对象存储，Reconciler 校验后更新 `SUCCEEDED`。
8. 前端展示时间线、配置快照、资源、日志和结果下载。
9. 重复提交、取消、Worker 重启、Job 409、GPU 集群短暂不可用分别执行故障场景。

### 9.4 退出条件

- 成功、参数失败、镜像失败、资源不足、超时、取消、K8s API 短暂失败均有明确结果。
- 没有重复 Job、重复结果或越权 Artifact。
- Job 被清理后，结果仍可从持久化存储读取。
- 试点运行至少完成一轮重启恢复和取消确认演练。

## 10. M7：AIPhaMedX 运行时命名与生产强化

### 10.1 命名迁移顺序

只有 M0 命名盘点和 M6 试点闭环通过后，才执行运行时命名迁移：

1. 新建镜像仓库路径和镜像发布配置使用 `aiphamedx`。
2. 新建 Kubernetes namespace、Service、ServiceAccount、Job name prefix 和 labels 使用 `aiphamedx`。
3. Reconciler 同时读取新旧 labels/annotations，并记录命名版本。
4. 新对象存储前缀只用于新运行；历史对象保持原路径。
5. 前端非敏感偏好采用新 key 写入、旧 key 回退；认证 Token 不做无条件复制。
6. 更新 README、部署文档、示例配置、镜像模板、CI/CD 和告警规则。
7. 旧资源停止新建后，观察一个完整保留周期，再决定是否清理旧 namespace/Secret/Service。

### 10.2 生产强化工作包

- Scheduler/Reconciler 多副本、数据库锁/租约和 leader 竞争。
- Prometheus 指标：最老排队时间、调度延迟、Job 创建延迟、镜像拉取、结果上传、GPU 时间、失败分类和成本维度。
- 镜像扫描、digest 校验、Secret 轮换、Pod securityContext、NetworkPolicy 和 Registry 权限。
- PostgreSQL、Redis、MinIO 备份恢复和死信队列处理。
- 资源基准：镜像大小、启动时间、模型加载时间、GPU 执行时间、并发峰值和失败率。

### 10.3 验收

- 任何新建平台资源不再默认使用旧产品 slug。
- 旧运行仍能查询、对账、下载结果和完成清理。
- 任一 Scheduler 副本退出不会丢失或重复执行 Attempt。
- 告警能区分排队拥塞、调度失败、Job 失败、结果上传失败和 GPU 健康异常。

## 11. M8：灰度发布、回滚与旧路径退役

### 11.1 灰度顺序

1. 内部管理员用户开启 `frontend_workspace_v2` 和 `frontend_runs_v2`。
2. 仅试点工具开启 `scheduler_run_model` 和 `scheduler_k8s_reconciler`。
3. 选择一个真实项目执行成功、失败、取消和重试场景。
4. 扩大到内部项目，再扩大到低风险外部项目。
5. 至少观察一个完整运行保留周期和一次备份恢复窗口。
6. 评审后决定默认开启、继续灰度或回滚。

### 11.2 回滚原则

- 前端回滚只关闭 `frontend_*_v2`，旧页面和旧接口保持可用。
- 调度回滚只关闭新 Scheduler/Reconciler Feature Flag；已经创建的 Attempt 由兼容 Reconciler 继续收尾，不强行切换执行中的 Job。
- 数据库迁移只允许向前兼容；原则上不回滚已创建的 Run/Attempt 表，改由旧投影和读取兼容继续提供服务。
- 新旧镜像并存，不能删除旧 digest 或覆盖旧 tag。
- 发现数据一致性、越权、重复 Job、结果丢失或取消失效时，立即停止扩大灰度。

### 11.3 旧路径退役条件

满足以下条件后，才考虑将旧路径改为只读：

- 新运行模型默认承载所有新任务至少一个稳定版本周期。
- 旧 Task、WorkflowRun、ExecutionRecord 和 Artifact 查询均有兼容测试。
- 旧 `sciminer` 资源没有未完成运行，或仍有兼容 Reconciler 管理。
- 用户已完成新运行中心迁移，支持文档和运维手册已更新。
- 有明确的数据保留、镜像保留和旧 namespace 清理计划。

## 12. 任务分解与责任边界

| 工作流 | 主要责任 | 关键交付 |
| --- | --- | --- |
| 领域/后端 | 后端负责人 | Run/Attempt/Event/Outbox、状态机、兼容投影 |
| 调度 | 调度负责人 | Scheduler、Admission、租约、重试、Reconciler |
| 执行适配 | 执行负责人 | Gateway、K8s Adapter、Job manifest、结果收集 |
| 前端平台 | 前端负责人 | AIPhaMedX Shell、Design Tokens、项目上下文、响应式 |
| 运行体验 | 前端/产品 | `/runs`、时间线、日志、Artifact、错误诊断 |
| 基础设施 | 平台/运维 | GPU 集群、Registry、MinIO、RBAC、备份、监控 |
| 测试验收 | QA/算法代表 | 契约测试、故障演练、模型输入输出、视觉回归 |
| 品牌迁移 | 产品/平台 | Logo、文案、仓库/镜像/服务命名、兼容矩阵 |

## 13. 依赖、风险与应对

| 风险 | 触发信号 | 应对 |
| --- | --- | --- |
| 新旧状态不一致 | 页面显示成功但 Artifact 不可用 | 以 Reconciler 和结果校验为最终门槛，禁止仅凭 Pod 退出码成功 |
| Outbox 重复投递 | 同一任务出现多个 Attempt | 唯一键、消费租约、幂等 Job 名称和重复消费测试 |
| GPU 环境未准备好 | Job 一直 Pending 或镜像无法拉取 | M6 前完成 GPU/Registry/Secret/Device Plugin 预检，不拿应用代码代替基础设施验收 |
| 品牌改名破坏旧集成 | 旧工具包、Job 或前端 Token 无法读取 | 分层命名、双读兼容、旧镜像和协议留存，不做全量替换 |
| 前端重构绑定旧字段 | 新页面大量读取 `extra_data` | 只允许读取 Run domain model，由适配层完成旧数据投影 |
| 迁移范围膨胀 | 同时要求改仓库、Python 包、协议和数据库 | 将仓库目录、Python 包和协议命名拆成独立决策，不阻塞首个 GPU 闭环 |
| 观测不足无法容量规划 | 只有 Worker 健康，没有队列和 Job 时间 | M0 先埋点，M7 以真实数据制定容量，不提前承诺 SLA |

## 14. 统一验收清单

### 功能

- [ ] 新运行提交立即返回 `run_id`，不等待计算完成。
- [ ] 运行状态能够展示排队、调度、提交、运行、成功、失败、取消和重试等待。
- [ ] 独立工具运行和工作流运行进入同一运行中心。
- [ ] 输入、输出、日志和 Artifact 均经过项目权限控制。
- [ ] 结果持久化并校验成功后才显示成功。

### 可靠性

- [ ] 重复提交不会创建重复 Run。
- [ ] 重复消费不会创建重复 Attempt 或 Job。
- [ ] Scheduler/Reconciler 重启后能继续处理未完成运行。
- [ ] K8s API、Redis、Worker 和 GPU 集群暂时不可用时不丢任务。
- [ ] 取消可以确认外部 Job 停止，失败时用户能看到明确原因。

### 前端与品牌

- [ ] 新页面、页面 title、Logo、邮件和文档使用 `AIPhaMedX`。
- [ ] 新平台自有资源默认使用 `aiphamedx`，旧资源仍可查询。
- [ ] 工作台、项目、运行中心和运行详情完成桌面/平板/移动验收。
- [ ] 状态颜色同时有文字和图标，加载、空态、失败和无权限状态完整。
- [ ] 静态 DEMO 的模拟行为没有被误接入真实生产流程。

### 运维与安全

- [ ] Kubernetes 使用最小 RBAC、受控 ServiceAccount 和 Secret 引用。
- [ ] 镜像使用固定 digest，旧 digest 可用于历史运行重放。
- [ ] 有队列、Job、GPU、存储、结果上传和失败分类指标。
- [ ] PostgreSQL、Redis 和 MinIO 完成备份恢复演练。
- [ ] 灰度、回滚和旧路径退役步骤经过演练并有记录。

## 15. 下一步执行顺序

本实施计划落地后的第一轮工作只做 M0，不直接进入代码大规模改造：

1. 建立命名注册表和外部消费者清单。
2. 选择并冻结一个 GPU `k8s_job` 试点工具。
3. 记录当前任务/工作流/执行记录/Artifact 的真实状态链路。
4. 确认 Run/Attempt/Event/Outbox 的字段和旧 Task 映射。
5. 确认前端 V2 的视觉验收页面和品牌资产。
6. M0 评审通过后，再进入 M1 数据模型迁移。

在 M0 未完成前，不执行仓库目录重命名、批量 K8s 资源重命名、全局品牌字符串替换或生产 Feature Flag 切换。
