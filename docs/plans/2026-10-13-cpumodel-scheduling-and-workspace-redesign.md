# AIPhaMedX 调度重构与研究工作台重设计方案

> 版本：V1.0 设计方案｜日期：2026-10-13
> 适用项目：`cpumodel_sciminer` 现有平台 → AIPhaMedX 产品化重构

## 1. 目标与结论

本方案同时解决三件事：

1. 将现有 `Task + Worker/Executor` 执行链路逐步重构为可恢复、可观测、可扩展的计算调度系统。
2. 将现有 Vue 前端从“功能入口集合”重设计为以项目和研究运行记录为中心的研究工作台，并吸收 `AIPhaMedX_Clickable_Prototype.html` 已验证的布局语言和交互节奏。
3. 将产品对外品牌和平台自有命名统一到 `AIPhaMedX` / `aiphamedx`，同时为历史数据、外部集成和现有运行资源保留兼容读取能力。

总体决策：**保留已有业务资产和执行适配器，重构调度领域；保留现有前端路由兼容，重做 App Shell、工作台首页、项目空间和运行详情体验；以 AIPhaMedX 作为新的正式品牌。** 不采用一次性推倒重写，也不把静态原型直接搬进生产代码。

当前代码已经具备以下可复用能力：

- 任务创建、列表、详情、取消、重试、日志和项目权限控制。
- Celery/Redis 异步执行、队列优先级、资源档案、Worker capability 和资源租约。
- 本地/MinIO 存储、Artifact 绑定、执行结果收集和受控下载。
- `k8s_job` 执行类型、Kubernetes Job manifest、状态/日志/取消/产物收集适配器。
- 工作流定义、运行记录、节点调度和运行详情页面。

当前主要问题不是“缺少所有功能”，而是两个层次混在一起：

- 调度语义被分散在 `Task`、`extra_data`、Celery Worker 和各类 Executor 中。
- 用户界面按模块和历史功能组织，项目、数据、工作流、运行和结果之间的研究上下文不够连续。
- 静态 DEMO 的视觉层次、工作区导航、项目导向和运行快照表达优于当前正式前端，但其行为仍是本地模拟，不能直接当作真实产品实现。

### 1.1 品牌目标与兼容边界

**已确定的产品目标**：所有新用户可见界面和产品材料以 `AIPhaMedX` 为正式名称；平台新建且由本项目控制的机器资源优先使用 `aiphamedx` slug。代码和部署改名按迁移计划分阶段执行，不做全仓库无差别字符串替换。

| 命名层次 | 目标 | 迁移原则 |
| --- | --- | --- |
| 对外品牌 | `AIPhaMedX` | 新页面标题、Logo、登录页、邮件、帮助文档和产品文案统一使用 |
| 平台自有机器 slug | `aiphamedx` | 新仓库/镜像/服务/Kubernetes 资源和新对象前缀优先使用；存量资源先盘点再迁移 |
| 仓库目录与远程仓库 | 目标名 `aiphamedx` | 纳入品牌迁移，但作为独立切换步骤；先更新 CI、部署、开发文档和协作者工作区，再更改远程地址/目录 |
| Python 包边界 | 暂时继续使用 `app` | 不与产品品牌强绑定；只有独立评估导入路径、Alembic、Worker 和插件兼容后才考虑改名 |
| 旧产品名 | `CPUModel` / `cpumodel` | 新用户界面不再使用；历史配置、存储键和路由按兼容方案逐步退役 |
| 旧平台 slug | `sciminer` / `scitool` | 不作为新资源默认命名；存量镜像、Job、Artifact、协议和数据库值仍可读取 |

以下迁移决策需要先完成消费者和数据盘点，不能仅凭字符串外观决定：

- `aidd.sciminer/*` 工具包、请求和结果协议属于共享数据契约。先盘点生产者/消费者和已发布包，再决定是否发布新的协议命名空间；旧值必须继续可读，不能把命名替换当作协议升级。
- `sciminer.io/*` Kubernetes labels/annotations 是运行中 Job 的查询索引。新前缀可作为迁移候选，但需让 Reconciler 在整个兼容期识别新旧前缀，并验证旧 Job 完成和回收后再退役旧值。
- `cpumodel_*`、`scitool:*` Redis/localStorage key 需逐 key 分类。非敏感偏好可采用新 key 优先、旧 key 回退；认证凭据不得无条件复制，需遵循登录态和 Token 安全策略。
- 已发布镜像使用 digest 固定且不可变；新镜像可使用 `aiphamedx/*` 路径，旧 digest 继续支持历史运行重放和合规留存。
- 数据库表名、外部 API 字段、Artifact 类型标识和对象存储路径先保持兼容。新运行可以使用平台自有的 `aiphamedx` 前缀，但不批量移动历史对象或修改用户提交的工具包内容。

## 2. 现状审查

### 2.1 静态 DEMO 值得保留的设计语言

`docs/dev/AIPhaMedX_Clickable_Prototype.html` 体现出一套更适合科研平台的产品方向：

- 深蓝侧栏 + 浅色内容区，主色为青绿色，和“计算/研究工作台”定位一致。
- 左侧以工作区为核心，有品牌、工作区切换、分组导航、状态计数和用户区。
- 顶部有面包屑、全局搜索、通知和主要操作，页面上下文明确。
- 工作台首页采用“欢迎区 + 快速入口 + 进行中运行 + 项目/数据/资源概览”的编排，而非单纯的统计卡片。
- 项目、工作流、工具、数据集、运行详情形成连续的研究路径。
- 运行详情通过节点步骤、配置快照、输入 checksum、验证器版本和产物表达“可追溯运行”。
- 文案明确区分“示例/原型”和“真实计算”，没有把模拟状态伪装成生产结果。

### 2.2 当前正式前端需要解决的问题

当前 `AppShell.vue` 以通用侧栏导航为主，入口包括工作台、工具、任务、工作流和管理后台；`workspace/index.vue` 主要是项目、关注任务和近期 Artifact 的列表组合；工作流和任务页面能力较丰富，但顶层信息架构仍是“模块导航”。

主要问题：

1. **产品主线不够突出**：项目、数据、工作流、运行和结果没有被组织成一条主路径，用户需要在多个顶级菜单之间跳转。
2. **首页缺少研究上下文**：没有把“当前项目、最近运行、需要关注的失败、最近产物、计算资源状态”放在同一视图中。
3. **视觉层次偏弱**：当前通用页面和 Ant Design 默认控件占比高，卡片、间距、标题层级和强调色不够统一。
4. **运行状态表达不足**：已有任务状态和工作流状态，但没有以运行时间线、节点进度、资源快照、产物校验和错误分类为中心呈现。
5. **工具中心与运行中心割裂**：工具列表适合管理，研究人员更需要“选择工具 → 配置输入 → 运行 → 查看结果”的连续体验。
6. **静态 DEMO 与正式应用语言不一致**：两套侧栏、颜色、卡片和页面节奏并存，后续会增加维护成本。

### 2.3 后端现状需要保留和重构的部分

保留：

- `backend/app/execution` 的执行契约、Kubernetes/SSH Adapter 和 transport seam。
- `backend/app/tasks/resource_profile.py` 的资源快照思想。
- `backend/app/tasks/resource_admission.py`、Worker capability、租约和项目资源配额能力。
- 现有 Artifact、MinIO、权限、工作流和任务 API 的业务兼容面。

重构：

- `backend/app/models/tasks.py` 中以旧任务状态为中心的聚合模型。
- `backend/app/tasks/service.py` 中同时承担创建、准备、资源评估、入队和分发的宽接口。
- `extra_data` 中不断增长的调度元数据。
- 任务级状态与执行器真实状态之间缺少统一事件和 Attempt 模型的问题。

## 3. 目标架构

### 3.1 四个领域层

```text
研究工作台 / 项目空间
        │
        ▼
业务控制面：Project、Workflow、Run、Artifact、权限、查询
        │  提交 ExecutionIntent
        ▼
调度控制面：Queue、Admission、ClusterRoute、Attempt、Retry、Reconcile
        │  调用统一 Execution Contract
        ▼
执行面 Adapter：Kubernetes Job / SSH Job / Local / Remote API
        │
        ▼
持久化数据面：PostgreSQL、Redis/Queue、MinIO、Registry、Metrics/Logs
```

四层职责必须保持清晰：

- **业务控制面**只负责用户意图、项目权限、工作流和结果查询，不直接拼接 Kubernetes YAML。
- **调度控制面**只负责是否可调度、调度到哪里、何时重试、如何取消和如何恢复，不实现模型算法。
- **执行面 Adapter**只负责把统一执行请求转换为具体运行时，并回传执行事实。
- **持久化数据面**保存任务意图、尝试、事件、资源快照和 Artifact，不让状态只存在 Celery 或 Pod 内存中。

### 3.2 推荐的深模块与接口

#### A. `ExecutionIntent` 模块

对业务控制面暴露一个小接口：提交已校验的运行意图，返回稳定的 `run_id`。模块内部负责参数 schema、输入 Artifact、工具版本和资源档案的快照化。

接口需要保证：

- 输入已经经过项目权限和工具契约校验。
- 运行意图不可变；修改参数必须创建新的运行。
- 同一 `project_id + idempotency_key` 不重复创建运行。
- 不允许用户直接提交任意镜像、命令、挂载路径或 Kubernetes 字段。

#### B. `Scheduler` 模块

调度器对外只暴露“接收一个可调度运行、返回调度决策”的接口，内部隐藏队列、配额、Worker capability、GPU 集群健康和租约细节。

调度决策至少包含：

- `accepted`、`waiting`、`rejected` 三种结果。
- `reason_code` 和面向用户的原因摘要。
- 目标 `cluster_id`、队列、资源档案和租约信息。
- 调度版本和决策时间，便于复现和审计。

调度器不替代 Kubernetes Scheduler；它只做任务级的目标集群/队列/资源规格决策。

#### C. `ExecutionGateway` 模块

复用现有 `backend/app/execution` 作为统一执行 seam。调度器只看到以下生命周期：

- `submit(request) -> external_handle`
- `inspect(external_handle) -> execution_state`
- `reconcile(external_handle) -> execution_state`
- `cancel(external_handle)`
- `logs(external_handle, cursor)`
- `collect_result(external_handle)`

Kubernetes、SSH、Local 和 Remote API 是 Adapter，不把任何一种执行器泄漏到业务控制面。

#### D. `RunReconciler` 模块

负责把数据库中的运行尝试与外部执行事实进行收敛：

- 调度服务重启后重新发现未完成的 Attempt。
- 外部 Job 已创建但数据库未保存句柄时，通过幂等键恢复。
- 只有结果上传并校验成功后，才将运行置为成功。
- 取消时先进入 `CANCELLING`，确认外部工作负载停止后再进入 `CANCELLED`。

### 3.3 目标领域模型

| 实体 | 作用 | 关键字段 |
| --- | --- | --- |
| `Run` | 用户可见的一次研究运行 | `run_id`、`project_id`、`workflow_run_id`、`status`、`priority`、`created_at` |
| `RunAttempt` | 一次实际执行尝试 | `attempt_id`、`run_id`、`attempt_no`、`adapter_type`、`external_id`、`status`、退出信息 |
| `RunResource` | 运行时资源快照 | CPU、内存、GPU 数量、GPU 型号/显存、超时、节点约束 |
| `RunArtifact` | 输入、输出、日志和检查点引用 | URI、大小、checksum、语义类型、访问策略 |
| `RunEvent` | 状态变化和调度事实 | 事件类型、旧状态、新状态、原因、时间、脱敏 payload |
| `ModelRelease` | 可执行模型/工具版本 | 版本、image digest、参数 schema、资源档案、发布状态 |
| `ClusterCapability` | 执行集群能力快照 | 集群、队列、GPU 型号、显存、容量、健康、更新时间 |

兼容策略：现有 `Task` 先作为旧读模型和 API 投影；新运行模型落地后，旧任务通过 `legacy_task_id` 或投影读取，不立即删除历史数据。

### 3.4 目标状态机

```text
CREATED → QUEUED → DISPATCHING → SUBMITTED → RUNNING
   │         │          │            │          │
   └→ FAILED ├→ CANCELLED           ├→ QUEUED  ├→ RETRY_WAIT
             └→ FAILED              └→ FAILED  ├→ CANCELLING
                                                └→ SUCCEEDED / FAILED
```

状态规则：

- `QUEUED` 表示等待资源或调度，不代表执行器已经收到任务。
- `DISPATCHING` 只能由调度器进入，必须使用 `run_id + attempt_no` 幂等创建。
- `SUBMITTED` 表示外部工作负载已创建但尚未开始计算。
- `RETRY_WAIT` 由平台任务级重试预算控制，Kubernetes Job 默认 `backoffLimit=0`，避免双重重试。
- `SUCCEEDED` 必须同时满足外部执行成功、结果存在、checksum/结构校验通过和结果元数据持久化成功。
- 终态默认不可回到运行态；重新运行创建新的 `Run` 或明确的 rerun 记录。

### 3.5 数据一致性和可靠性

第一阶段采用数据库事务 + Outbox：

1. 在同一事务中写入 `Run`、`RunResource`、输入 Artifact 快照和 `DispatchOutbox`。
2. Outbox publisher 读取未发送事件，投递到 Redis/Celery 或后续消息队列。
3. 调度器消费后写入 `RunAttempt` 和调度决策，并使用唯一键防止重复领取。
4. Adapter 创建外部 Job 时使用稳定的幂等名称和 annotation。
5. Reconciler 周期性扫描 `DISPATCHING/SUBMITTED/RUNNING/CANCELLING`，将数据库状态收敛到执行事实。

不在第一阶段引入复杂工作流编排引擎、跨区域公平队列或 GPU 共享调度；先保证一个 GPU 集群的闭环可靠。

## 4. 后端重构分阶段方案

### 阶段 0：冻结契约与观测基线

目标：不改变用户行为，先让现状可测量。

- 固定新旧状态映射表、旧 Task API 兼容规则和错误码。
- 为现有任务补齐 `dispatch_id`、`attempt_id`、执行器类型、队列、资源快照和 trace ID 的结构化日志。
- 统计提交到入队、入队到开始、开始到完成、结果上传和取消确认的耗时。
- 明确测试环境的 Direct、Celery、Kubernetes 三条执行模式。

### 阶段 1：引入 Run/Attempt/Outbox

目标：先改变持久化模型，不改变前端主流程。

- 新增 `Run`、`RunAttempt`、`RunResource`、`RunEvent`、`DispatchOutbox` 数据模型。
- 现有任务创建服务写入新模型，并继续生成旧 `Task` 投影。
- 旧任务详情读取新模型的兼容字段，确保历史任务仍可查。
- 为提交 API 增加 `Idempotency-Key` 或请求体中的 `idempotency_key`。

### 阶段 2：调度器与 Reconciler 独立化

目标：把调度从任务创建服务和 Celery Worker 中抽离。

- `Scheduler` 负责配额、优先级、资源档案、Worker/Cluster capability 和队列选择。
- `RunReconciler` 负责外部状态同步、结果收集、取消确认和异常恢复。
- Celery 只作为第一阶段的持久化消息传输，不再作为领域状态来源。
- Direct 模式只用于本地开发和测试，通过相同的 `ExecutionGateway` contract 工作。

### 阶段 3：独立 GPU 集群闭环

目标：在真实环境验证蓝图的最小生产闭环。

- 业务集群只调用受控的执行 Adapter 或 GPU 集群内执行代理。
- 通过 cluster capability 表达 GPU 型号、显存、节点池、污点和可用队列。
- Job manifest 固定 image digest、资源 requests/limits、超时、TTL、ServiceAccount、对象存储输出前缀和业务 labels。
- 完成提交、排队、Job 创建、状态/日志、结果持久化、取消、Worker 重启、GPU 集群短暂不可用的验收。

### 阶段 4：生产强化

- 多副本 Scheduler/Reconciler，数据库锁或租约确保一次 Attempt 只有一个协调者。
- 镜像扫描、签名、不可变发布、RBAC、网络策略和 Secret 轮换。
- 队列等待、Job 创建延迟、镜像拉取、GPU 时间、失败分类和项目成本指标。
- 备份恢复演练、死信处理、容量基准和 SLA 告警。

## 5. 前端重设计方案

### 5.1 产品定位

前端以 **AIPhaMedX** 为品牌，从“平台功能导航”转为“项目驱动的研究计算工作台”：

```text
工作台总览 → 选择项目 → 准备数据/工作流 → 创建运行
                                      ↓
                           运行中心 → 结果与 Artifact → 复用/导出
```

工具、模型和管理后台仍然存在，但它们是能力资源，不应和研究运行争夺一级视觉焦点。

### 5.2 新信息架构

左侧导航建议调整为：

**工作区**

- 工作台
- 项目
- 运行
- 数据与 Artifact

**构建**

- 工作流
- 工具与模型

**治理**（管理员可见）

- 计算资源
- 工具注册
- 系统与审计

底部保留：主题、帮助/快捷键、用户菜单。

导航不再把“任务”和“工作流”完全割裂：

- `运行` 是统一入口，展示独立工具运行和工作流运行。
- 工作流页面用于构建和配置；运行页面用于观察执行事实。
- 项目空间中的“运行”使用项目过滤条件进入统一运行中心。

建议路由兼容映射：

| 现有路由 | 新定位 | 迁移策略 |
| --- | --- | --- |
| `/workspace` | `/workspace` 工作台总览 | 保留路径，重做页面内容 |
| `/projects/:projectId` | 项目总览 | 保留路径，增加项目上下文导航 |
| `/tasks` | `/runs` 运行中心 | 新增 `/runs`，旧 `/tasks` 重定向 |
| `/tasks/:id` | `/runs/:runId` | 旧任务详情兼容跳转到运行详情 |
| `/workflow` | 工作流构建器 | 保留路径 |
| `/workflow/runs/:runId` | 运行详情 | 与统一运行详情共享模块 |
| `/tools` | 工具与模型目录 | 保留路径，强化“开始运行”入口 |

### 5.3 App Shell 视觉系统

参考静态 DEMO，但不复制其内联 CSS，改为正式的 Design Tokens：

#### 色彩

- `navy-900`：侧栏和深色品牌区域。
- `navy-700`：侧栏 hover/active。
- `teal-500`：主行动色、运行中状态和选中指示。
- `blue-500`：链接、信息和资源类信息。
- `amber-500`：等待、资源不足和需要关注。
- `red-500`：失败、权限和危险操作。
- `surface-0/1/2`：页面、卡片、输入区三个层级。

#### 布局

- 侧栏宽度 `248px`，收起宽度 `72px`，与 DEMO 的导航密度一致。
- 顶栏高度 `68px`，固定显示面包屑、全局搜索、通知、帮助和用户入口。
- 主内容最大宽度 `1440px`，页面左右内边距在桌面端 `32px`，小屏降为 `20px`。
- 页面使用 8px spacing grid；卡片圆角 10–14px，避免过度圆润。
- 用细边框和轻阴影区分层级，不使用大面积渐变和无意义装饰。

#### 字体和内容层级

- 页面标题 24–28px；区块标题 15–18px；辅助说明 12–13px。
- 关键状态使用颜色 + 文本 + 图标三重表达，不能只用颜色。
- 运行 ID、镜像 digest、checksum、版本号使用等宽字体。
- 所有“演示/模拟/未连接”状态必须用明确标签，不能伪装成真实运行。

### 5.4 核心页面布局

#### A. 工作台首页 `/workspace`

结构：

1. 顶部欢迎区：当前工作区、最近访问项目、`新建项目`、`开始一次运行`。
2. 运行状态带：运行中、排队中、需要关注、近 7 天成功率。
3. 主区域左侧：进行中的运行时间线，展示项目、工作流/工具、阶段、等待原因、预计下一动作。
4. 主区域右侧：项目快捷入口、最近 Artifact、计算资源状态。
5. 底部：最近项目卡片和“继续上次研究”入口。

首页不堆叠十几个统计卡片；每个模块必须回答一个操作问题：现在有什么在运行、我需要处理什么、我可以从哪里继续。

#### B. 项目空间 `/projects/:projectId`

采用静态 DEMO 的 workspace switcher 和项目上下文，但项目页增加二级导航：

- 总览
- 研究对话/计划
- 工作流
- 运行
- 数据与 Artifact
- 谱系
- 设置

项目头部固定展示项目名称、目标摘要、成员/权限、最近更新时间和主要操作。所有列表默认带项目过滤，不让用户误以为跨项目数据是同一研究上下文。

#### C. 运行中心 `/runs`

统一呈现独立工具运行和工作流运行：

- 顶部筛选：项目、状态、运行类型、工具/模型、时间。
- 左侧或顶部状态分组：全部、运行中、排队中、需要关注、已完成。
- 主列表以运行卡片/紧凑表格切换呈现，默认卡片包含状态、项目、阶段、资源、创建时间和最近事件。
- 失败项直接展示失败分类和下一步操作，避免只显示“失败”。

#### D. 运行详情 `/runs/:runId`

沿用静态 DEMO 的“节点运行记录 + 配置快照”思路，但绑定真实数据：

- 顶部：运行名称、项目、状态、运行 ID、操作按钮。
- 状态时间线：Created、Queued、Dispatched、Submitted、Running、Completed/Failed。
- 左栏：节点/Attempt 列表，显示每个节点的状态、耗时、重试次数、日志入口。
- 右栏：运行配置快照、镜像 digest、模型版本、资源请求、集群、输入 checksum。
- 下方：实时日志、结果 Artifact、质量验证摘要、失败诊断和审计事件。
- 运行成功后显示“结果质量”而不只显示“任务成功”；科学有效性和人工复核要独立表达。

#### E. 工作流构建器 `/workflow`

保留现有画布和节点配置能力，视觉上使用新的 App Shell 和右侧 Inspector：

- 左侧为节点/工具库，中间为画布，右侧为属性和输入输出契约。
- 顶部只保留保存、验证、运行、版本和撤销/重做。
- 运行按钮明确区分“运行当前节点”和“运行整个工作流”。
- 所有节点展示输入/输出 Artifact 类型、资源档案、超时、重试策略。

#### F. 工具与模型目录 `/tools`

保留管理能力，但面向研究用户优化：

- 卡片展示能力标签、输入类型、输出类型、推荐资源、版本和可运行状态。
- 工具详情首屏显示“适合解决什么问题”和“开始运行”，管理字段放到版本/治理面板。
- 运行表单分为输入、参数、资源预览、结果预期四段，提交前显示不可变运行快照。

### 5.5 可复用前端模块

建立少量深模块，避免每个页面重新拼装状态：

- `WorkspaceShell`：品牌、工作区切换、导航、顶栏和全局状态。
- `ProjectContext`：项目上下文、成员权限、项目级过滤和二级导航。
- `RunStatusModel`：统一旧 Task、WorkflowRun、RunAttempt 的展示状态映射。
- `RunTimeline`：状态事件、Attempt、耗时、错误和重试的统一呈现。
- `ArtifactBrowser`：输入/输出 Artifact、版本、语义类型、checksum、下载和谱系。
- `ResourceSummary`：资源档案、GPU/CPU/内存、队列、集群和等待原因。
- `ExecutionInspector`：日志、配置快照、外部 Job、失败诊断和审计事件。

页面只组合这些模块，不直接读取 `extra_data` 或自行判断后端状态。

### 5.6 前端数据契约

前端新的运行模型至少需要：

```text
RunSummary
- id, project, name, kind, status
- progress, current_stage, waiting_reason
- created_at, started_at, finished_at
- resource_summary, latest_event

RunDetail
- summary
- attempts[]
- events[]
- inputs[], outputs[], logs
- execution_snapshot
- quality_summary
- permissions
```

兼容阶段由前端 domain 层把旧 `Task` 和 `WorkflowRun` 投影成 `RunSummary/RunDetail`，页面不感知后端是否处于双写期。

### 5.7 响应式与可访问性

- `>=1200px`：完整侧栏、三栏工作台和运行详情双栏。
- `768–1199px`：侧栏收起，卡片改为两列，运行详情改为上下布局。
- `<768px`：侧栏变为抽屉，顶栏只保留项目、搜索和用户菜单，运行节点和日志采用折叠面板。
- 所有状态颜色提供文本和图标；键盘可访问导航、搜索、筛选、时间线和日志。
- 长 ID、checksum 和错误信息支持复制、折叠和完整内容弹层。

## 6. 前后端迁移策略

### 6.1 双模型兼容期

后端：新 `Run` 作为写模型，旧 `Task` 作为兼容投影。
前端：新 `/runs` 页面优先读取新查询接口，旧 `/tasks` 继续可用并跳转到兼容详情。

双写期必须记录：

- `legacy_task_id ↔ run_id`
- `workflow_run_id ↔ run_id`
- `attempt_id ↔ external_id`
- 旧状态 ↔ 新状态

### 6.2 发布顺序

1. 先发布 AIPhaMedX Design Tokens、Logo、文案、页面 title 和 App Shell；对非敏感旧前端偏好提供回退读取。
2. 发布工作台首页和项目空间新版布局，继续使用现有任务/Artifact API。
3. 后端启用 Run/Attempt/Outbox 双写，前端增加 `/runs` 查询和详情。
4. 完成旧 slug 消费者盘点和兼容测试后，再为新镜像/Job/Service 使用 `aiphamedx` 命名；Reconciler 在兼容期同时识别存量资源。
5. 切换调度器和 Reconciler，先对一个 K8s Job 工具版本启用。
6. 完成真实 GPU 集群闭环后，逐步迁移其他工具和工作流节点。
7. 独立切换仓库远程地址和目录名 `aiphamedx`，同步 CI、镜像流水线、部署清单、文档和开发者工作区；不得在活跃开发者仍依赖旧目录时强制移动。
8. 稳定运行一个版本周期后，才下线旧任务页面和旧显示名；旧数据与协议按各自兼容策略保留读取。

### 6.3 Feature Flag

建议至少设置：

- `frontend_workspace_v2`
- `frontend_runs_v2`
- `scheduler_run_model`
- `scheduler_outbox`
- `scheduler_k8s_reconciler`
- `scheduler_gpu_cluster_route`
- `brand_aiphamedx_ui`
- `runtime_aiphamedx_resources`

Feature Flag 必须按用户、项目或工具版本逐步放量，不能只按环境硬切换。

## 7. 测试与验收

### 后端

- 状态机：合法/非法转换、终态、取消确认、重试预算。
- 幂等：重复提交、重复消费、重复创建 Job、调度器重启恢复。
- 调度：资源不足保持等待，不兼容资源明确拒绝；配额和优先级不会互相绕过。
- Adapter：Kubernetes submit/inspect/reconcile/cancel/logs/result 的契约测试。
- 结果：对象存在、大小/checksum/schema 验证成功后才进入 `SUCCEEDED`。
- 权限：跨项目任务、日志、Artifact、运行详情和下载地址均拒绝越权访问。
- 故障：Redis 短暂不可用、数据库提交后进程退出、Job 创建返回 409、GPU 集群不可用、Worker 重启。

### 前端

- `WorkspaceShell` 在桌面、收起、平板和移动布局下保持导航可用。
- `RunStatusModel` 对旧 Task、WorkflowRun 和新 Run 的状态映射测试。
- 工作台空态、加载态、部分接口失败和权限不足状态。
- 运行详情时间线、Attempt 重试、日志加载、结果下载和 Artifact 权限。
- 工作流“当前节点运行”和“整个工作流运行”按钮语义不混淆。
- 视觉回归：侧栏、首页、运行列表、运行详情、工具目录五个关键页面。

### 端到端验收场景

1. 用户在项目中上传输入 Artifact。
2. 选择一个固定 digest 的 GPU 工具版本。
3. 提交运行并立即得到 `run_id`。
4. 页面显示 `QUEUED → DISPATCHING → SUBMITTED → RUNNING`。
5. Kubernetes Job 在目标 GPU 节点创建并回传日志。
6. 结果上传、校验、展示并可授权下载。
7. 用户取消一次运行，页面最终显示 `CANCELLED`，外部 Job 已停止。
8. 调度 Worker 重启后，运行状态和结果不丢失。

## 8. 不在本次方案范围内

- 不重写具体 AIDD 算法、模型内部推理和科学质量规则。
- 不在第一阶段引入跨区域调度、加权公平队列、GPU 共享/MIG 或检查点恢复的完整产品能力。
- 不把静态 HTML DEMO 直接转换为生产页面，也不保留其本地模拟数据逻辑。
- 不因为视觉重设计而修改已有业务权限模型和工具注册流程。
- 不在没有真实容量数据前承诺复杂的成本计费和 SLA 数字。
- 不在本轮直接修改 Python 顶级包、数据库表、外部 API/协议字段、历史 Artifact 类型或对象存储路径；仓库名与目录名属于目标迁移，但在独立切换步骤执行。

## 9. 近期产物与执行建议

建议按以下顺序形成下一轮设计和实现任务：

1. `Run/RunAttempt/RunEvent/DispatchOutbox` 数据模型与旧 `Task` 映射表。
2. 新状态机和失败分类表。
3. AIPhaMedX 品牌资产、完整命名盘点和“可直接更名 / 需兼容 / 暂不迁移”清单。
4. `/runs` 查询/详情接口契约，以及旧任务兼容投影。
5. `WorkspaceShell`、工作台首页、项目上下文导航的视觉原型。
6. 单个 `k8s_job` 工具版本的真实 GPU 集群端到端验收。
7. 前端 V2 逐页迁移、AIPhaMedX 品牌迁移和视觉回归基线。

第一优先级不是先做更多页面，而是先建立统一运行模型和真实运行状态。这样前端重设计不会再次绑定旧 `Task` 字段，后端调度重构也能直接服务于用户可理解的运行体验。
