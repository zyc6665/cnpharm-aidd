# AIDD 研究项目平台生产化设计

## 1. 背景与目标

CPUModel 当前已经具备工具管理、任务执行、工作流、AIDD Agent Run、文件产物和科研白板，但核心产品形态仍是工具平台。Agent 以一次性运行和计划为中心，缺少项目级记忆、多轮会话、流式轨迹、审批、结构化 Artifact 和断线恢复。科研白板以抽屉承载编辑器，也不适合长期空间组织。

本设计将平台演进为：

> 研究项目优先、对话驱动、可复现制品落地的 AIDD 研究平台。

首要用户是计算化学和 AIDD 研究员。管理员与算法工程师继续使用独立管理面。

黄金流程为：

1. 创建研究项目并描述目标。
2. Agent 澄清输入并检查蛋白/配体数据。
3. Agent 生成结构化、可解释的计划。
4. 用户按风险和成本审批计划。
5. 平台执行工具工作流并实时展示轨迹。
6. 结果沉淀为可追溯 Artifact。
7. Artifact 可进入科研白板和版本化报告。

首月以 LVpocket 的“蛋白结构到口袋识别”作为唯一完整黄金闭环。

## 2. 范围

### 2.1 首月范围

- 组织、项目、项目成员和项目事实的基础模型。
- 项目内多会话、消息、Agent 事件、计划版本和审批。
- SSE 流式对话与轨迹，WebSocket 运行状态。
- Tool Package v1 规范、模板、校验器和 LVpocket 参考包。
- CPU/NVIDIA 运行变体；海光 DCU 声明为“适配完成，待硬件验收”。
- SSH 执行器的提交、状态、日志、取消、超时和产物回传闭环。
- Protein Structure、Pocket Result、File、Run Report 四类 Artifact。
- 简洁研究项目首页和项目研究对话页。
- 科研白板改为项目内整页路由。
- PostgreSQL、Redis、MinIO 容器化开发与验收环境。
- 旧 API 保留一个迁移周期，通过兼容层和功能开关切换。
- 其他现有模型转换为 Tool Package 并标注验证等级，不承诺完整黄金验收。

### 2.2 明确延期

- 实时多人协作。
- 完整报告编辑器和双人审批流程。
- LDAP、OIDC、SAML。
- Runner Agent、Slurm、Kubernetes 执行器。
- 国产数据库和国产中间件替换。
- 海光 DCU 真实硬件验收。
- 全量 OpenTelemetry 平台。
- 全部现有模型的同等级生产验收。

## 3. 架构原则

采用演进式模块化单体，不在首月拆微服务。

- FastAPI 仍作为一个部署单元，但按 Project、Conversation、Agent、Tool Package、Execution、Artifact、Canvas、Identity、Audit 划分深模块。
- 模块不得直接操作其他模块的数据表，跨模块通过应用服务、稳定 DTO 和领域事件协作。
- PostgreSQL 是业务事实数据源。
- Redis 仅承担事件缓冲、队列协调、短期锁和实时状态。
- MinIO 保存不可变输入、计算产物和快照。
- Celery 负责后台协调，不直接承担模型计算。
- 模型计算通过 `ExecutionPort` 交给外部计算面。

### 3.1 控制面

- Vue 3：项目首页、研究对话、Agent 轨迹、Artifact、整页科研白板和管理面。
- FastAPI：领域 API、权限、审批、计划、工具注册、执行协调和审计。
- PostgreSQL：项目、会话、计划、审批、执行、Artifact 元数据和谱系。
- Redis：SSE 事件缓冲、WebSocket 状态和后台协调。
- MinIO：文件、模型产物、报告和项目快照。

### 3.2 计算面

- 首发 `SSHExecutionAdapter`，使用密钥引用和跳板机。
- 后续 Runner、Slurm、Kubernetes 实现相同 `ExecutionPort`。
- CPU、NVIDIA CUDA、海光 DCU 是同一 Tool Package 的运行变体。
- Agent 和工具包不得感知 SSH、Slurm 或 Kubernetes 细节。

## 4. 核心领域模型

### 4.1 组织与项目

- `Organization`：私有化部署默认一个组织，保留未来多组织边界。
- `Project`：目标、状态、模型策略、联网策略和数据策略。
- `ProjectMember`：负责人、编辑者、运行者、只读者。
- `ProjectFact`：区分已确认事实、Agent 假设、计算结果和外部证据。

项目状态：`draft`、`active`、`completed`、`archived`、`frozen`。

### 4.2 会话与 Agent

- `Conversation`：属于项目，一个项目可有多个独立研究线程。
- `Message`：保存版本化结构内容，不只保存 Markdown。
- `ConversationBranch`：编辑历史消息或修改目标时创建分支。
- `AgentRun`：一次 Agent 处理周期。
- `AgentEvent`：有序、可恢复的结构化轨迹。
- `PlanVersion`：不可变的工具步骤、参数、资源、风险和策略快照。
- `Approval`：审批主体、范围、结果、意见和时间。

Agent 事件至少包括：

- `goal_understood`
- `input_required`
- `input_validated`
- `evidence_found`
- `plan_drafted`
- `approval_required`
- `execution_submitted`
- `execution_progress`
- `artifact_created`
- `analysis_completed`
- `recoverable_error`
- `terminal_error`

### 4.3 Tool Package 与执行

- `ToolPackage`：工具身份和发布生命周期。
- `ToolPackageVersion`：不可变版本、签名和 SBOM。
- `ToolVariant`：CPU、NVIDIA、DCU 的镜像、驱动、入口和资源。
- `ExecutionRun`：执行器、节点、状态、日志、重试和资源统计。

Tool Package 状态：`draft`、`validating`、`review`、`published`、`deprecated`、`retired`。

硬件验证状态：

- `verified`
- `adapted_pending_hardware_validation`
- `unavailable`

### 4.4 Artifact 与谱系

- `Artifact`：类型、对象存储键、哈希、版本、来源和访问策略。
- `ArtifactLineage`：输入、输出、工具、计划和执行之间的关系。
- `ResearchBoard`：属于项目，节点引用 Artifact、证据、会话、工作流、报告或文本。
- `ReportVersion`：项目快照、章节、引用、审阅和冻结状态，首月只提供最小运行报告。

首月 Artifact 类型：

- `protein_structure`
- `pocket_result`
- `file`
- `run_report`

## 5. Agent 与实时交互

用户只面对一个研究助手。输入检查、文献检索、规划、执行监控和结果分析是内部能力模块，不显示虚构的多 Agent 讨论。

Agent 状态机：

`received → clarifying → context_ready → planning → awaiting_approval → executing → observing → analyzing → completed|failed|canceled`

### 5.1 结构化工作轨迹

平台不展示模型隐藏思维链。前端展示：

- 当前阶段。
- 简短决策依据。
- 输入和输出。
- 引用和证据。
- 工具、参数、资源和耗时。
- 审批与错误恢复事件。

### 5.2 通信

- SSE：消息增量、Agent 事件、引用、审批卡片和 Artifact。
- WebSocket：任务进度、资源状态、取消和重试。
- 每个事件带单调递增序号；客户端携带最后序号恢复。
- 事件消费必须幂等，断线后不能重复消息或丢失审批。

### 5.3 记忆边界

- 会话记忆只覆盖当前线程。
- 项目记忆只读取已确认事实、已批准结论和相关 Artifact。
- 用户偏好独立保存。
- 不允许自动跨项目读取。
- Agent 推测必须明确标记，不能自动成为项目事实。

### 5.4 分级授权

- 读取项目元数据、校验文件等低风险操作可自动执行。
- GPU/DCU、批量计算、联网、数据外发、覆盖结果和导出必须审批。
- 用户可以为当前项目授予有期限的授权。
- 审批结果保存为不可变计划和策略快照。

## 6. Tool Package v1

标准目录：

```text
tool-package/
├── tool.yaml
├── schemas/
│   ├── parameters.schema.json
│   ├── inputs.schema.json
│   └── outputs.schema.json
├── variants/
│   ├── cpu.yaml
│   ├── nvidia-cuda.yaml
│   └── haiguang-dcu.yaml
├── runner/
│   ├── entrypoint.sh
│   └── result_parser.py
├── examples/
│   ├── input/
│   ├── expected/
│   └── request.json
├── tests/
│   ├── test_contract.py
│   └── test_golden.py
├── README.md
├── LICENSE
└── AGENTS.md
```

`tool.yaml` 声明工具身份、版本、AIDD 阶段、语义输入输出、Artifact 类型、参数 Schema、运行变体、资源、健康检查、结果解析、网络权限、许可证和黄金样例。

外部 CI 负责：

- Schema 和语义契约校验。
- 运行变体一致性测试。
- 黄金样例。
- SBOM、漏洞扫描和镜像签名。

Codex 和 Claude Code 可以从模板生成、校验和打包工具，但不能绕过管理员审核直接发布。

## 7. 前端信息架构

### 7.1 `/workspace`

研究项目首页只保留：

- 新建项目。
- 继续最近研究。
- 待审批和失败任务。
- 最近 Artifact。
- 项目搜索和状态筛选。

全局任务统计进入任务页，运营统计进入管理面。

### 7.2 `/projects/:projectId`

- 左侧窄栏：项目、会话线程和新建会话。
- 中间：研究对话、审批卡片、Artifact 预览。
- 右侧可折叠检查器：项目事实、运行轨迹、文件和计划。
- 支持流式回答、停止、继续、编辑并分支、重新生成、附件、引用、审批、后台运行和历史搜索。

### 7.3 科研白板

使用 `/projects/:projectId/boards/:boardId`。

- 删除抽屉编辑模式。
- 画布占据项目主区域。
- 左侧对象工具栏和右侧选择检查器均可收起。
- 提供保存状态、撤销/重做、缩放、专注模式。
- 节点可引用 Artifact、证据、会话、工作流、报告和文本。
- 白板表达“知道什么和依据是什么”，工作流表达“如何执行”。

### 7.4 设计系统

- 保留 Ant Design Vue 作为底层组件能力。
- 建立 AIDD 产品 Token 和状态组件。
- 减少卡片、边框、默认蓝色按钮和装饰。
- 移除 Google Fonts 等公网依赖。
- 桌面提供完整能力；平板可用；手机仅承诺聊天、审批、状态和报告查看。

## 8. 信创与部署

首个基线：海光 x86_64、麒麟/UOS、海光 DCU。当前只有 NVIDIA 硬件，因此：

- NVIDIA 标记为 `verified`。
- 海光 DCU 标记为 `adapted_pending_hardware_validation`。
- 未完成真实硬件黄金样例前不得宣称 DCU 已支持。

网络采用双模式：离线环境完整运行，联网能力通过受控连接器开启。首期 PostgreSQL/Redis 上线，后续国产数据库与中间件替换通过专项兼容测试完成。

生产容器包括前端、FastAPI、Celery、PostgreSQL、Redis 和 MinIO。模型运行在外部计算节点。API 和 Worker 不挂载 Docker Socket。

## 9. 错误、安全与审计

- API 返回稳定错误码、用户消息和关联 ID。
- 临时错误有限重试；契约和输入错误立即停止。
- 资源不足允许排队或经审批切换变体。
- 原始失败记录不可覆盖。
- 项目 ACL、组织边界和最小权限。
- SSH 密钥只通过密钥引用加载。
- 外部访问经过脱敏、预览、审批和审计。
- Artifact 导出与外发分别授权。
- 审计记录只追加。
- 按等保三级可演进架构设计，首月不宣称通过正式测评。

## 10. 迁移与上线

- 为每个现有用户创建默认迁移项目。
- 关联现有文件、白板、工作流和 Agent Run。
- 历史任务保持不可变。
- 迁移遵循“新增结构 → 回填 → 双读校验 → 功能开关切换 → 稳定后清理”。
- 旧 API 保留一个迁移周期并标记 deprecated。

恢复目标为 RPO 不超过 1 小时、RTO 不超过 4 小时。PostgreSQL、MinIO、配置和密钥分别备份，并要求定期恢复演练。

## 11. 首月验收标准

- 登录后三次操作内开始或继续研究。
- 首次 Agent 流式反馈不超过 2 秒。
- 后台任务状态延迟不超过 3 秒。
- 断线恢复不重复消息、不丢审批和运行事件。
- LVpocket NVIDIA 黄金样例端到端通过。
- 项目、聊天、审批、SSH 执行、Artifact 和白板引用形成闭环。
- 白板 200 节点仍可交互。
- 无 i18n 警告、未处理 Promise、布局重叠和横向溢出。
- 关键流程具有 API、组件和浏览器 E2E 测试。
- 其他模型明确显示“已导入”“可运行”或“生产已验证”等级。

## 12. 实施顺序

- 第 1 周：项目、会话、事件、审批、PostgreSQL/Redis/MinIO 和迁移基础。
- 第 2 周：Tool Package v1、LVpocket、SSH 执行器和 Artifact。
- 第 3 周：项目首页、研究对话、SSE、审批和执行观察。
- 第 4 周：整页白板、其他模型包转换、E2E、离线部署和灰度切换。
