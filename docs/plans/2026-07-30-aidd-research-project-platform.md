# AIDD Research Project Platform Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在一个月内将现有工具平台演进为项目优先、对话驱动的 AIDD 研究平台，并以 LVpocket NVIDIA 口袋识别完成首条生产级纵向闭环。

**Architecture:** 保持 FastAPI 模块化单体和 Vue 3 单页应用，通过 Project、Conversation、Agent、Tool Package、Execution、Artifact、Canvas 等深模块建立稳定边界。PostgreSQL 保存事实状态，Redis 提供实时事件缓冲，MinIO 保存不可变 Artifact，SSH 是首发执行适配器，旧 API 通过兼容层保留一个迁移周期。

**Tech Stack:** FastAPI、SQLAlchemy 2、Alembic、PostgreSQL、Redis、Celery、MinIO、SSE、WebSocket、Vue 3、Pinia、Vue Router、Ant Design Vue、Vitest、pytest。

---

## 实施约束

- 使用当前工作区和现有分支，不创建额外 worktree。
- 未经用户明确要求，不执行 Git commit、push 或分支操作。
- 每项功能先写失败测试，再写最小实现。
- 首月只让 LVpocket 达到“生产已验证”；其他工具只迁移包格式和验证等级。
- 不在首月实现 LDAP、实时协同、完整报告编辑器、Runner、Slurm、Kubernetes、国产数据库和 DCU 真机验收。
- 任何旧 API 删除都必须晚于功能开关稳定期。

## 第 1 周：项目、会话与实时事件基础

### Task 1: 建立组织、项目和项目成员领域模型

**Files:**
- Create: `backend/app/models/projects.py`
- Create: `backend/app/schemas/projects.py`
- Create: `backend/app/services/project_access.py`
- Create: `backend/app/api/v1/projects.py`
- Create: `backend/alembic/versions/20260730_02_research_projects.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/api/v1/__init__.py`
- Test: `test/test_projects_api.py`

**Step 1: 写失败测试**

覆盖以下契约：

```python
async def test_project_owner_can_create_and_read_project(client, auth_headers):
    response = await client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "Pocket study", "goal": "Identify ligandable pockets"},
    )
    assert response.status_code == 200
    project_id = response.json()["data"]["id"]
    detail = await client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert detail.json()["data"]["membership"]["role"] == "owner"
```

同时覆盖跨用户 404、只读成员禁止修改、项目状态枚举和组织隔离。

**Step 2: 验证测试失败**

Run: `pytest test/test_projects_api.py -q`

Expected: FAIL，项目路由或模型不存在。

**Step 3: 实现最小模型**

模型至少包含：

```python
class Organization(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "organizations"
    name = Column(String(160), nullable=False)
    slug = Column(String(100), nullable=False, unique=True, index=True)

class Project(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "projects"
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    goal = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    model_policy = Column(JSON, nullable=False, default=dict)
    data_policy = Column(JSON, nullable=False, default=dict)

class ProjectMember(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "project_members"
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(32), nullable=False)
```

`project_access.py` 提供 `require_project_role(project_id, allowed_roles)`，禁止各路由复制权限判断。

**Step 4: 迁移和测试**

Run:

```bash
alembic upgrade head
pytest test/test_projects_api.py -q
pytest test/test_alembic_migration_dry_run.py -q
```

Expected: PASS，Alembic head 为 `20260730_02`。

### Task 2: 回填默认迁移项目并建立旧资源关联

**Files:**
- Create: `backend/app/services/project_migration.py`
- Create: `backend/app/cli/backfill_projects.py`
- Create: `backend/alembic/versions/20260730_03_legacy_project_links.py`
- Modify: `backend/app/models/agent.py`
- Modify: `backend/app/models/files.py`
- Modify: `backend/app/models/workflows.py`
- Test: `test/test_project_backfill.py`

**Step 1: 写失败测试**

创建有文件、Agent Run、工作流和白板的旧用户，运行 backfill 两次，断言：

- 只创建一个默认项目。
- 所有旧资源关联到该项目。
- 第二次运行不产生重复关联。
- 历史任务内容和时间戳不变。

**Step 2: 验证测试失败**

Run: `pytest test/test_project_backfill.py -q`

**Step 3: 实现幂等回填**

优先给资源增加 nullable `project_id`，回填完成和双读验证后再考虑收紧 nullable。不要在本次迁移删除 `owner_id` 或 `user_id`。

CLI 提供：

```bash
cd backend && python -m app.cli.backfill_projects --dry-run
cd backend && python -m app.cli.backfill_projects --apply
```

输出用户数、项目数、资源关联数和无法归属记录。

**Step 4: 测试回填和回滚路径**

Run: `pytest test/test_project_backfill.py test/test_projects_api.py -q`

Expected: PASS。

### Task 3: 建立会话、消息、事件、计划版本和审批模型

**Files:**
- Create: `backend/app/models/conversations.py`
- Create: `backend/app/schemas/conversations.py`
- Create: `backend/app/services/conversations.py`
- Create: `backend/app/api/v1/conversations.py`
- Create: `backend/alembic/versions/20260730_04_project_conversations.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/api/v1/__init__.py`
- Test: `test/test_project_conversations_api.py`

**Step 1: 写失败测试**

覆盖：

- 项目成员创建多个会话。
- 消息按不可变版本保存。
- 编辑历史消息创建 `ConversationBranch`，不覆盖原消息。
- `AgentEvent.sequence` 在单个 Agent Run 中唯一递增。
- 断线恢复查询 `after_sequence` 只返回后续事件。
- 审批只允许具备 `runner` 或 `owner` 权限的成员执行。

**Step 2: 运行失败测试**

Run: `pytest test/test_project_conversations_api.py -q`

**Step 3: 实现模型和 API**

端点：

```text
GET    /projects/{project_id}/conversations
POST   /projects/{project_id}/conversations
GET    /conversations/{conversation_id}/messages
POST   /conversations/{conversation_id}/messages
POST   /messages/{message_id}/branch
GET    /agent-runs/{run_id}/events?after_sequence=N
POST   /plan-versions/{plan_id}/approve
POST   /plan-versions/{plan_id}/reject
```

消息 `content` 使用区块数组，例如 `text`、`citation`、`artifact_ref`、`approval_ref`，同时保留纯文本摘要用于搜索。

**Step 4: 迁移与测试**

Run:

```bash
alembic upgrade head
pytest test/test_project_conversations_api.py -q
```

Expected: PASS。

### Task 4: 实现可恢复 SSE Agent 事件流

**Files:**
- Create: `backend/app/realtime/agent_events.py`
- Create: `backend/app/api/v1/agent_stream.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/v1/__init__.py`
- Test: `test/test_agent_event_stream.py`

**Step 1: 写失败测试**

使用测试客户端创建三个持久化事件，携带 `Last-Event-ID: 1` 连接 SSE，断言只收到 2、3；重复连接不创建新事件；无权限用户返回 404。

**Step 2: 验证测试失败**

Run: `pytest test/test_agent_event_stream.py -q`

**Step 3: 实现持久化优先的事件流**

SSE 格式固定为：

```text
id: 42
event: execution_progress
data: {"run_id":"...","payload":{"progress":35}}
```

数据库保存事件事实，Redis Pub/Sub 只负责唤醒连接。断线后先补数据库事件，再订阅 Redis。每 15 秒发送注释心跳。

**Step 4: 验证恢复和资源释放**

Run: `pytest test/test_agent_event_stream.py -q`

Expected: PASS，测试结束无悬挂异步任务。

## 第 2 周：Tool Package、执行器和 Artifact

### Task 5: 定义 Tool Package v1 模型、Schema 和校验器

**Files:**
- Create: `backend/app/tool_packages/__init__.py`
- Create: `backend/app/tool_packages/schemas.py`
- Create: `backend/app/tool_packages/loader.py`
- Create: `backend/app/tool_packages/validator.py`
- Create: `backend/app/models/tool_packages.py`
- Create: `backend/app/schemas/tool_packages.py`
- Create: `backend/app/api/v1/tool_packages.py`
- Create: `backend/alembic/versions/20260730_05_tool_packages_artifacts.py`
- Modify: `backend/app/services/tool_contracts.py`
- Test: `test/test_tool_package_contract.py`
- Test: `test/test_tool_package_api.py`

**Step 1: 写失败测试**

使用临时目录构造合法和非法包，覆盖：

- 缺少 `tool.yaml`。
- 未声明语义输入输出。
- 运行变体引用未声明 Artifact 类型。
- NVIDIA 变体缺少驱动/设备声明。
- DCU 未真机验证时只能使用 `adapted_pending_hardware_validation`。
- 三种变体输出契约必须一致。
- 未签名包不能发布。

**Step 2: 运行失败测试**

Run: `pytest test/test_tool_package_contract.py test/test_tool_package_api.py -q`

**Step 3: 实现 Pydantic v2 Schema**

核心类型：

```python
class Accelerator(str, Enum):
    CPU = "cpu"
    NVIDIA_CUDA = "nvidia_cuda"
    HAIGUANG_DCU = "haiguang_dcu"

class ToolVariantManifest(BaseModel):
    accelerator: Accelerator
    executor_types: list[Literal["container", "cli", "remote_job"]]
    image: str | None = None
    entrypoint: list[str]
    resources: ResourceSpec
    validation_status: ValidationStatus
```

现有 `build_tool_contract` 改为读取 Tool Package 规范，同时保留旧 `ToolVersion.config` 适配器。

**Step 4: 测试**

Run:

```bash
pytest test/test_tool_package_contract.py test/test_tool_package_api.py test/test_tool_contracts.py -q
```

Expected: PASS，旧工具契约测试不回归。

### Task 6: 创建可供 Codex/Claude Code 使用的工具包模板

**Files:**
- Create: `example/tool-package-template/tool.yaml`
- Create: `example/tool-package-template/schemas/parameters.schema.json`
- Create: `example/tool-package-template/schemas/inputs.schema.json`
- Create: `example/tool-package-template/schemas/outputs.schema.json`
- Create: `example/tool-package-template/variants/cpu.yaml`
- Create: `example/tool-package-template/variants/nvidia-cuda.yaml`
- Create: `example/tool-package-template/variants/haiguang-dcu.yaml`
- Create: `example/tool-package-template/runner/entrypoint.sh`
- Create: `example/tool-package-template/runner/result_parser.py`
- Create: `example/tool-package-template/tests/test_contract.py`
- Create: `example/tool-package-template/AGENTS.md`
- Create: `docs/guides/tool-package-authoring.md`
- Test: `test/test_tool_package_template.py`

**Step 1: 写模板自验证测试**

测试直接用生产校验器加载模板，断言所有必需文件存在、示例请求合法、三种变体的 Artifact 输出一致。

**Step 2: 验证测试失败**

Run: `pytest test/test_tool_package_template.py -q`

**Step 3: 实现模板和 AI 指令**

`AGENTS.md` 要求代码智能体：

- 不修改平台契约版本。
- 不写入明文密钥、IP 或宿主路径。
- 同时生成测试、README、LICENSE 和黄金样例说明。
- 对未测试硬件使用待验收状态。
- 运行 `python -m app.tool_packages.validator <path>`。

**Step 4: 验证模板**

Run: `pytest test/test_tool_package_template.py -q`

Expected: PASS。

### Task 7: 将 LVpocket 升级为参考 Tool Package

**Files:**
- Create: `example/LVpocket/tool-package/tool.yaml`
- Create: `example/LVpocket/tool-package/schemas/parameters.schema.json`
- Create: `example/LVpocket/tool-package/schemas/inputs.schema.json`
- Create: `example/LVpocket/tool-package/schemas/outputs.schema.json`
- Create: `example/LVpocket/tool-package/variants/cpu.yaml`
- Create: `example/LVpocket/tool-package/variants/nvidia-cuda.yaml`
- Create: `example/LVpocket/tool-package/variants/haiguang-dcu.yaml`
- Create: `example/LVpocket/tool-package/runner/result_parser.py`
- Create: `example/LVpocket/tool-package/tests/test_golden_contract.py`
- Modify: `example/LVpocket/platform_tool.ssh_job.json`
- Test: `test/test_lvpocket_tool_package.py`

**Step 1: 写失败测试**

固定公开 PDB、来源、许可证、SHA-256 和预处理规则。断言：

- 输入识别为 `protein_structure`。
- 输出至少包含 `pocket_result` 和 `run_report`。
- NVIDIA 标记 `verified`。
- DCU 标记 `adapted_pending_hardware_validation`。
- 结果解析器拒绝缺少 `result.json` 或校验失败的输出。

**Step 2: 验证失败**

Run: `pytest test/test_lvpocket_tool_package.py -q`

**Step 3: 实现参考包**

复用现有 `platform_run.sh` 和 SSH 配置，不在本任务重写模型。把旧 JSON 保留为 deprecated 兼容入口，并指向 Tool Package 版本。

**Step 4: 执行静态和真实 NVIDIA 验证**

Run:

```bash
pytest test/test_lvpocket_tool_package.py -q
python -m app.tool_packages.validator ../example/LVpocket/tool-package
```

真实运行命令只在已配置 SSH 凭据的验收环境执行，并把运行 ID、输入哈希、工具包版本和输出哈希写入验收记录。

### Task 8: 深化执行器端口并适配现有 SSH Job

**Files:**
- Create: `backend/app/execution/contracts.py`
- Create: `backend/app/execution/port.py`
- Create: `backend/app/execution/service.py`
- Create: `backend/app/execution/adapters/ssh.py`
- Create: `backend/app/models/executions.py`
- Modify: `backend/app/tasks/executors/ssh_job.py`
- Modify: `backend/app/tasks/executor.py`
- Test: `test/test_execution_port.py`
- Test: `test/test_ssh_execution_adapter.py`

**Step 1: 写失败测试**

用 FakeExecutionAdapter 覆盖 submit、status、logs、cancel、recover_artifacts。SSH 适配测试 mock transport，断言密钥内容不出现在请求 DTO、日志或数据库模型中。

**Step 2: 验证失败**

Run: `pytest test/test_execution_port.py test/test_ssh_execution_adapter.py -q`

**Step 3: 实现稳定端口**

```python
class ExecutionPort(Protocol):
    async def submit(self, request: ExecutionRequest) -> ExecutionHandle: ...
    async def status(self, execution_id: str) -> ExecutionStatus: ...
    async def logs(self, execution_id: str, cursor: str | None) -> LogChunk: ...
    async def cancel(self, execution_id: str) -> None: ...
    async def collect_artifacts(self, execution_id: str) -> list[ProducedArtifact]: ...
```

现有 `SSHJobExecutor` 的传输和产物处理可以被适配器组合使用，但 Agent 和 Project 模块只能依赖 `ExecutionPort`。

**Step 4: 回归**

Run:

```bash
pytest test/test_execution_port.py test/test_ssh_execution_adapter.py -q
pytest test/test_task_executor.py test/test_ssh_job_executor.py -q
```

若实际文件名不同，使用 `rg --files test | rg 'ssh|executor'` 选择现有回归套件。

### Task 9: 建立类型化 Artifact 和谱系

**Files:**
- Create: `backend/app/models/artifacts.py`
- Create: `backend/app/schemas/artifacts.py`
- Create: `backend/app/services/artifacts.py`
- Create: `backend/app/api/v1/artifacts.py`
- Modify: `backend/app/storage/base.py`
- Modify: `backend/app/storage/minio_backend.py`
- Modify: `backend/alembic/versions/20260730_05_tool_packages_artifacts.py`
- Test: `test/test_typed_artifacts_api.py`
- Test: `test/test_artifact_lineage.py`

**Step 1: 写失败测试**

覆盖项目权限、SHA-256 去重、不可变版本、输入输出谱系、过期对象、MinIO 键不能由用户直接指定，以及跨项目引用拒绝。

**Step 2: 验证失败**

Run: `pytest test/test_typed_artifacts_api.py test/test_artifact_lineage.py -q`

**Step 3: 实现 Artifact 服务**

所有 Artifact 创建必须经过：内容哈希 → 对象写入 → 元数据事务 → 谱系写入。对象键由服务生成：

```text
organizations/{org_id}/projects/{project_id}/artifacts/{artifact_id}/{version}/{filename}
```

MinIO 失败时数据库不得留下可用状态的 Artifact。

**Step 4: 回归**

Run:

```bash
pytest test/test_typed_artifacts_api.py test/test_artifact_lineage.py test/test_file_artifacts_api.py -q
```

Expected: PASS。

## 第 3 周：项目工作台与研究对话

### Task 10: 将 Agent 服务接入项目会话和审批状态机

**Files:**
- Create: `backend/app/agents/aidd/project_service.py`
- Create: `backend/app/agents/aidd/event_publisher.py`
- Modify: `backend/app/agents/aidd/graph_state.py`
- Modify: `backend/app/agents/aidd/graph_nodes.py`
- Modify: `backend/app/agents/aidd/service.py`
- Modify: `backend/app/api/v1/agents.py`
- Test: `test/test_project_agent_lifecycle.py`

**Step 1: 写失败测试**

构造项目、会话和蛋白 Artifact，断言 Agent：

- 缺少蛋白时发布 `input_required`，不创建执行。
- 输入合法时生成不可变计划版本。
- 未审批不得调用 ExecutionPort。
- 审批后提交 LVpocket，并按顺序发布执行事件。
- Artifact 完成后发布分析摘要。
- 修改目标创建新计划分支，旧计划不变。

**Step 2: 验证失败**

Run: `pytest test/test_project_agent_lifecycle.py -q`

**Step 3: 实现项目 Agent 应用服务**

复用现有 LangGraph 规划节点，但把数据库写入、审批和执行放在应用服务中。Prompt 只返回结构化计划和简短依据，不输出隐藏思维链。

**Step 4: 回归旧 Agent API**

Run:

```bash
pytest test/test_project_agent_lifecycle.py test/test_aidd_agent_api.py test/test_aidd_langgraph_nodes.py -q
```

Expected: PASS，旧接口响应增加 deprecation 元数据但不破坏字段。

### Task 11: 重构 `/workspace` 为研究项目首页

**Files:**
- Create: `frontend/src/api/projects.ts`
- Create: `frontend/src/types/projects.ts`
- Create: `frontend/src/components/projects/ProjectList.vue`
- Create: `frontend/src/components/projects/ProjectCreateDialog.vue`
- Modify: `frontend/src/api/workspace.ts`
- Modify: `frontend/src/views/workspace/index.vue`
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`
- Test: `frontend/src/views/workspace/project-workspace.spec.ts`

**Step 1: 写失败组件测试**

mock 项目 API，断言首屏只显示新建项目、最近项目、待审批/失败任务和最近 Artifact；不显示旧的全局状态统计和常用工具区。

**Step 2: 验证失败**

Run: `cd frontend && npm test -- --run src/views/workspace/project-workspace.spec.ts`

**Step 3: 实现页面**

页面不使用嵌套卡片。最近项目采用紧凑列表，待审批使用状态行，主要操作为“新建项目”和“继续研究”。所有 API 具备 loading、empty、error、retry。

**Step 4: 组件与构建验证**

Run:

```bash
cd frontend && npm test -- --run src/views/workspace/project-workspace.spec.ts
cd frontend && npm run build
```

Expected: PASS。

### Task 12: 实现项目研究对话页

**Files:**
- Create: `frontend/src/api/conversations.ts`
- Create: `frontend/src/api/agent-stream.ts`
- Create: `frontend/src/types/conversations.ts`
- Create: `frontend/src/stores/project-conversation.ts`
- Create: `frontend/src/composables/useAgentEventStream.ts`
- Create: `frontend/src/views/projects/Research.vue`
- Create: `frontend/src/components/conversation/ConversationSidebar.vue`
- Create: `frontend/src/components/conversation/MessageTimeline.vue`
- Create: `frontend/src/components/conversation/MessageComposer.vue`
- Create: `frontend/src/components/conversation/AgentTrace.vue`
- Create: `frontend/src/components/conversation/PlanApprovalCard.vue`
- Create: `frontend/src/components/conversation/ProjectInspector.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/components/layout/AppShell.vue`
- Test: `frontend/src/views/projects/Research.spec.ts`
- Test: `frontend/src/composables/useAgentEventStream.spec.ts`

**Step 1: 写失败测试**

覆盖：

- 项目/会话/检查器三栏布局。
- 流式事件按 sequence 去重。
- 断线使用最后 sequence 重连。
- 审批卡片显示工具、参数、资源、预计时间和联网风险。
- 未具备运行权限时审批按钮禁用。
- 停止、重新生成、编辑并分支。
- 失败事件显示可操作重试状态。

**Step 2: 验证失败**

Run:

```bash
cd frontend && npm test -- --run src/views/projects/Research.spec.ts src/composables/useAgentEventStream.spec.ts
```

**Step 3: 实现流式交互**

SSE composable 保存 `lastEventId`，只把事件交给 store reducer；组件不得各自处理事件顺序。消息行尺寸稳定，工具轨迹默认折叠，不显示原始大日志。

**Step 4: 验证**

Run:

```bash
cd frontend && npm test -- --run src/views/projects/Research.spec.ts src/composables/useAgentEventStream.spec.ts
cd frontend && npm run build
```

Expected: PASS。

### Task 13: 建立共享 Artifact 前端渲染器

**Files:**
- Create: `frontend/src/types/artifacts.ts`
- Create: `frontend/src/api/artifacts.ts`
- Create: `frontend/src/components/artifacts/ArtifactRenderer.vue`
- Create: `frontend/src/components/artifacts/ProteinStructureArtifact.vue`
- Create: `frontend/src/components/artifacts/PocketResultArtifact.vue`
- Create: `frontend/src/components/artifacts/FileArtifact.vue`
- Create: `frontend/src/components/artifacts/RunReportArtifact.vue`
- Modify: `frontend/src/components/tasks/ResultVisualizationPanel.vue`
- Modify: `frontend/src/components/conversation/MessageTimeline.vue`
- Test: `frontend/src/components/artifacts/ArtifactRenderer.spec.ts`

**Step 1: 写失败测试**

断言四种 Artifact 使用类型注册表选择渲染器，未知类型显示稳定 fallback，文件 URL 必须经过受保护 API，不能直接拼接对象存储地址。

**Step 2: 验证失败**

Run: `cd frontend && npm test -- --run src/components/artifacts/ArtifactRenderer.spec.ts`

**Step 3: 实现注册表**

```typescript
const artifactComponents: Record<ArtifactType, Component> = {
  protein_structure: ProteinStructureArtifact,
  pocket_result: PocketResultArtifact,
  file: FileArtifact,
  run_report: RunReportArtifact,
}
```

复用现有 Molstar 和结果组件，不复制解析逻辑。

**Step 4: 验证**

Run:

```bash
cd frontend && npm test -- --run src/components/artifacts/ArtifactRenderer.spec.ts
cd frontend && npm run build
```

Expected: PASS。

## 第 4 周：整页白板、部署与上线加固

### Task 14: 将科研白板迁移为项目级整页路由

**Files:**
- Modify: `backend/app/models/workflows.py`
- Modify: `backend/app/api/v1/research_boards.py`
- Modify: `backend/app/schemas/research_boards.py`
- Modify: `backend/alembic/versions/20260730_02_research_projects.py`
- Create: `frontend/src/views/research-boards/List.vue`
- Create: `frontend/src/views/research-boards/Board.vue`
- Create: `frontend/src/components/research-boards/BoardInspector.vue`
- Create: `frontend/src/components/research-boards/BoardObjectPalette.vue`
- Modify: `frontend/src/views/research-boards/index.vue`
- Modify: `frontend/src/components/research-boards/ResearchBoardCanvas.vue`
- Modify: `frontend/src/router/index.ts`
- Test: `test/test_project_research_boards_api.py`
- Test: `frontend/src/views/research-boards/Board.spec.ts`

**Step 1: 写失败测试**

后端覆盖项目 ACL、跨项目 Artifact 引用拒绝和旧 owner 白板兼容。前端断言：

- 点击白板进入 `/projects/:projectId/boards/:boardId`。
- 编辑器不是 Drawer 或 Modal。
- 画布、对象工具栏、检查器和专注模式存在。
- Artifact 节点使用共享 `ArtifactRenderer`。
- 200 节点初始化不改变画布尺寸。

**Step 2: 验证失败**

Run:

```bash
pytest test/test_project_research_boards_api.py -q
cd frontend && npm test -- --run src/views/research-boards/Board.spec.ts
```

**Step 3: 实现整页白板**

列表页只负责创建、搜索和进入。Board 页面负责加载详情和编辑。删除原抽屉编辑路径，不保留两套状态。白板节点只保存引用 ID 和布局，不复制 Artifact 内容。

**Step 4: 回归**

Run:

```bash
pytest test/test_project_research_boards_api.py test/test_research_boards_api.py -q
cd frontend && npm test -- --run src/views/research-boards/Board.spec.ts src/components/__tests__/ResearchBoardCanvas.spec.ts
cd frontend && npm run build
```

Expected: PASS。

### Task 15: 完善 PostgreSQL、Redis、MinIO 和离线部署

**Files:**
- Modify: `docker-compose.prod.yml`
- Create: `docker-compose.aidd-dev.yml`
- Modify: `backend/.env.example`
- Modify: `backend/app/config.py`
- Modify: `frontend/index.html`
- Modify: `frontend/src/assets/styles/variables.less`
- Create: `docs/guides/aidd-offline-deployment.md`
- Test: `test/test_aidd_production_compose.py`
- Test: `frontend/test/no-public-runtime-dependencies.test.ts`

**Step 1: 写失败测试**

静态解析 Compose，断言：

- 生产数据库不是 SQLite。
- Redis 和 MinIO 有健康检查、持久卷和非默认凭据变量。
- API/Worker 不挂载 `/var/run/docker.sock`。
- 前端不引用 Google Fonts 或其他必须公网加载的资源。
- 后端启动依赖数据库、Redis、MinIO 健康。

**Step 2: 验证失败**

Run:

```bash
pytest test/test_aidd_production_compose.py -q
cd frontend && npm test -- --run test/no-public-runtime-dependencies.test.ts
```

**Step 3: 实现部署配置**

开发 Compose 可提供本地 PostgreSQL/Redis/MinIO；生产 Compose 只引用环境变量和 secret 文件，不写默认生产密码。文档包含离线镜像导入、依赖镜像、模型权重校验、备份和恢复演练。

**Step 4: 验证配置**

Run:

```bash
docker compose -f docker-compose.aidd-dev.yml config
docker compose -f docker-compose.prod.yml config
pytest test/test_aidd_production_compose.py -q
cd frontend && npm test -- --run test/no-public-runtime-dependencies.test.ts
```

若环境没有 Docker CLI，记录未执行项，但静态测试必须通过。

### Task 16: 转换其他现有模型并建立验证等级

**Files:**
- Create: `backend/app/tool_packages/migration.py`
- Create: `backend/app/cli/migrate_tool_packages.py`
- Modify: `frontend/src/views/admin/Tools.vue`
- Modify: `frontend/src/views/tools/Detail.vue`
- Create: `docs/tool-package-migration-report.md`
- Test: `test/test_tool_package_migration.py`
- Test: `frontend/test/tool-validation-status.test.ts`

**Step 1: 写失败测试**

从现有 `ToolVersion.config` 转换包描述，断言：

- 转换幂等。
- 未运行黄金样例的工具不能标记 `verified`。
- 管理面显示“已导入”“可运行”“生产已验证”或“待硬件验收”。
- 转换失败输出具体缺失契约字段。

**Step 2: 验证失败**

Run:

```bash
pytest test/test_tool_package_migration.py -q
cd frontend && npm test -- --run test/tool-validation-status.test.ts
```

**Step 3: 实现 dry-run 和 apply**

```bash
cd backend && python -m app.cli.migrate_tool_packages --dry-run
cd backend && python -m app.cli.migrate_tool_packages --apply
```

迁移报告列出工具、执行器、输入输出、变体、缺失项和验证等级。

**Step 4: 验证**

Run: `pytest test/test_tool_package_migration.py -q`

Expected: PASS。

### Task 17: 完成纵向 E2E、性能与故障恢复验收

**Files:**
- Create: `frontend/e2e/aidd-research-flow.spec.ts`
- Create: `frontend/playwright.config.ts`
- Create: `test/test_aidd_vertical_slice.py`
- Create: `test/performance/test_agent_event_latency.py`
- Create: `frontend/e2e/research-board-performance.spec.ts`
- Create: `docs/verification/aidd-first-month-acceptance.md`
- Modify: `frontend/package.json`

**Step 1: 写端到端失败测试**

浏览器流程：

1. 登录测试用户。
2. 创建项目和会话。
3. 输入研究目标并上传黄金蛋白 PDB。
4. 收到澄清/计划事件。
5. 审批 LVpocket 计划。
6. Fake SSH 或验收 SSH 执行完成。
7. 对话显示 Pocket Artifact。
8. 将 Artifact 加入整页白板。
9. 刷新和断线恢复后状态不丢失。

**Step 2: 验证测试失败**

Run:

```bash
pytest test/test_aidd_vertical_slice.py -q
cd frontend && npm run test:e2e -- aidd-research-flow.spec.ts
```

**Step 3: 修复纵向缺口，不新增范围**

只处理阻断闭环的问题。新功能建议写入后续 backlog，不在验收阶段扩展。

**Step 4: 性能与错误恢复**

验证：

- 首次 SSE 事件不超过 2 秒。
- 任务状态延迟不超过 3 秒。
- SSE 重连不重复事件。
- 白板 200 节点仍可缩放、平移和选择。
- API 失败都有用户可操作状态。

**Step 5: 全量验收**

Run:

```bash
pytest -q test
cd frontend && npm test -- --run
cd frontend && npm run build
cd frontend && npm run test:e2e
alembic heads
alembic current
git diff --check
```

Expected:

- 所有测试通过。
- Alembic 只有一个 head，数据库位于 head。
- 生产构建成功。
- 无 i18n 缺失、未处理 Promise 和页面 500。

## 功能开关与发布检查点

建议开关：

```text
AIDD_PROJECT_WORKSPACE_ENABLED
AIDD_PROJECT_CONVERSATIONS_ENABLED
TOOL_PACKAGE_V1_ENABLED
PROJECT_RESEARCH_BOARD_ENABLED
LEGACY_AIDD_API_ENABLED
```

发布顺序：

1. 部署新增表和兼容代码，所有新开关关闭。
2. dry-run 回填并核对数量。
3. 开启内部测试用户。
4. 完成 LVpocket 黄金闭环。
5. 分批开启普通用户。
6. 监控错误、事件延迟、审批失败和执行失败。
7. 稳定一个发布周期后再计划删除旧入口和旧字段。

## 完成定义

只有同时满足以下条件，首月计划才算完成：

- LVpocket NVIDIA 黄金闭环真实通过。
- DCU 明确显示待硬件验收，不作虚假支持声明。
- 新工作台和整页白板可通过功能开关启用。
- 旧数据可访问，旧 API 未被意外破坏。
- 项目权限、审批、事件恢复和 Artifact 谱系有回归测试。
- PostgreSQL、Redis、MinIO 部署配置可验证。
- 前后端全量测试、生产构建、浏览器 E2E 和迁移检查通过。
