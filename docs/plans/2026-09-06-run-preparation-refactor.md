# Run Preparation Refactor Implementation Plan

> 本计划按任务顺序小步执行，每个任务完成后运行对应回归测试。

**Goal:** 将工具运行前的输入准备、标准 Artifact 绑定、readiness 决策和 legacy 参数投影收敛到后端 `RunPreparation` 深模块。

**Architecture:** 新增 `backend/app/services/run_preparation.py`，先复用现有 `artifact_binding_resolver.py` 的纯策略能力。`tasks.service` 和 `workflow_scheduler` 保持对外 Interface 不变，内部逐步改为调用 `prepare_run()`，前端第一阶段保持兼容 payload，只用现有测试保护行为。

**Tech Stack:** Python 3、FastAPI、SQLAlchemy AsyncSession、Pydantic/dataclasses、pytest、Vue 3、TypeScript、Vitest。

---

## 执行约束

- 不做 git commit、push、reset；如需提交，必须由主人另行明确确认。
- 不做数据库迁移。
- 不改变公开 REST payload 的字段名。
- 不删除 legacy SSH/builtin 兼容逻辑，只移动归属位置。
- 每个任务完成后运行对应最小测试，再运行聚合回归。

## 当前执行进度

- 2026-09-06：已完成 Task 1-5 的第一批实现。
- 已新增 `backend/app/services/run_preparation.py`，覆盖 ArtifactVersion 绑定、阻塞决策、builtin 投影、legacy SSH 投影和 Tool Package v2 输入保留。
- 已将 `backend/app/tasks/service.py` 的标准输入准备切到 `prepare_run()`。
- 已补 `test/test_run_preparation.py`、`test/test_tasks_service_standard_inputs.py` 和 `test/test_workflow_scheduler.py` 回归。
- 已将 `backend/app/services/workflow_scheduler.py` 的普通 tool node、map node 和 loop body task 调度切到 `prepare_workflow_node_run()`，子任务会继承标准 `input_bindings`、`standard_input_uploads`、legacy/builtin 投影结果。
- 已删除 `workflow_scheduler.py` 中不再使用的 workflow input / Artifact 绑定解析 helper，绑定解析和投影逻辑集中在 `run_preparation.py`。
- 已恢复任务 API 对原始 `input_bindings` 的展示/追踪持久化，同时让 SSH/Remote executor 只在工具声明支持标准 Artifact 输入时消费这些绑定，避免 legacy 执行路径误走标准 request。
- 已通过当前聚合验证：后端相关回归 `180 passed`，前端运行面板/预检/绑定测试 `15 passed`，`git diff --check` 无输出。
- 2026-09-06：新增 `POST /api/v1/tasks/prepare-preview` 后端预览接口，复用 `prepare_run()` 返回 ready/blocked、绑定决策、legacy 文件投影和资源快照，但不创建任务、不调度任务、不记录工具使用次数。
- 已补任务 API 预览回归：raw protein + `require_prepared` 返回 blocked；prepared protein + legacy LVpocket 返回 projected `params.input_files`，两种场景均确认 `Task` 未落库且 direct runner 未调度。
- 已新增前端 `prepareTaskRun()` API 客户端和 `TaskRunPreparationPreview` 类型，前端后续可直接消费后端权威 Run Preparation 预览结果。
- 已将 standalone workflow node 运行入口接入 `prepareTaskRun()`：后端预览 ready 后才创建任务；blocked 时展示后端返回的准备失败原因，避免前端继续提交必失败任务。
- 已在 `useTasksStore` 增加 `prepareTaskRun()` 薄封装，供工具详情页等入口复用同一预览 API，且不改变任务列表状态。
- 已抽出前端 Run Preparation blocked 文案 helper，统一节点面板和后续工具详情页对后端预览失败原因的展示口径。
- 已将工具详情页运行入口接入 `tasksStore.prepareTaskRun()`，预览 blocked 时展示后端原因并停止创建任务，ready 时沿用原 `createTask()` 流程。

## Task 1: 建立 RunPreparation 回归测试基线

**Files:**
- Create: `test/test_run_preparation.py`
- Read: `test/test_workflow_scheduler.py`
- Read: `test/test_artifact_binding_resolver.py`
- Read: `test/test_tasks_service_standard_inputs.py`

**Step 1: 新增最小 fixture**

从 `test/test_workflow_scheduler.py` 复制并收敛以下 fixture/helper：

```python
@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    await engine.dispose()
```

**Step 2: 写 ArtifactVersion 输入 ready 测试**

覆盖 prepared protein + `require_prepared`：

```python
prepared = await prepare_run(
    db_session,
    input=RunPreparationInput(
        tool=tool,
        tool_version=tool.current_version,
        context=RunContext(surface="tool_detail", user_id=str(owner.id), project_id="project-1"),
        params={},
        file_ids=[],
        input_bindings={"protein": prepared_version.id},
        standard_input_uploads={},
    ),
)

assert prepared.ready is True
assert prepared.input_bindings == {"protein": prepared_version.id}
assert prepared.file_ids == [prepared_file.id]
assert prepared.binding_decisions["protein"]["status"] == "ready"
```

**Step 3: 写 ArtifactVersion 输入 blocked 测试**

覆盖 raw protein + `require_prepared`：

```python
prepared = await prepare_run(... input_bindings={"protein": raw_version.id} ...)

assert prepared.ready is False
assert prepared.blocked_reason
assert prepared.binding_decisions["protein"]["status"] == "needs_preparation"
assert prepared.binding_decisions["protein"]["suggested_tool_slug"] == "builtin-protein-preparation"
```

**Step 4: 写 builtin 投影测试**

覆盖 builtin protein preparation：

```python
assert prepared.params["builtin_inputs"] == {"protein_structure@1": protein_file.id}
assert prepared.file_ids == [protein_file.id]
```

**Step 5: 写 legacy SSH 投影测试**

覆盖 `params.input_files`：

```python
assert prepared.params["input_files"] == {"protein_pdb": "input/prepared.pdb"}
assert prepared.file_ids == [prepared_file.id]
```

**Step 6: 运行测试确认失败**

Run:

```bash
python -m pytest test/test_run_preparation.py -q
```

Expected: FAIL，因为 `backend/app/services/run_preparation.py` 尚不存在。

## Task 2: 新增 RunPreparation 模块骨架

**Files:**
- Create: `backend/app/services/run_preparation.py`
- Modify: `test/test_workflow_service_modules.py`

**Step 1: 增加模块存在性测试**

在 `test/test_workflow_service_modules.py` 的 `expected` 增加：

```python
"run_preparation.py",
```

**Step 2: 创建 dataclass 接口**

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

RunSurface = Literal["tool_detail", "standalone_node", "workflow_node", "agent_plan"]

@dataclass(frozen=True)
class RunContext:
    surface: RunSurface
    user_id: str
    project_id: str | None = None
    workflow_run_id: str | None = None
    workflow_definition_id: str | None = None
    workflow_node_id: str | None = None

@dataclass(frozen=True)
class RunPreparationInput:
    tool: Any
    tool_version: Any
    context: RunContext
    params: dict[str, Any]
    file_ids: list[str]
    input_bindings: dict[str, str]
    standard_input_uploads: dict[str, str]
    workflow_node: dict[str, Any] | None = None

@dataclass(frozen=True)
class PreparedRun:
    ready: bool
    project_id: str | None
    params: dict[str, Any]
    file_ids: list[str]
    input_bindings: dict[str, str]
    standard_input_uploads: dict[str, str]
    binding_decisions: dict[str, dict[str, Any]]
    blocked_reason: str | None = None
```

**Step 3: 暴露 prepare_run()**

实现最小函数签名：

```python
async def prepare_run(db: AsyncSession, *, input: RunPreparationInput) -> PreparedRun:
    ...
```

**Step 4: 运行测试确认进入具体断言失败**

Run:

```bash
python -m pytest test/test_run_preparation.py test/test_workflow_service_modules.py -q
```

Expected: `test_workflow_service_modules.py` PASS，`test_run_preparation.py` 在行为断言处 FAIL。

## Task 3: 迁入标准 ArtifactVersion 校验与绑定投影

**Files:**
- Modify: `backend/app/services/run_preparation.py`
- Read: `backend/app/tasks/service.py:97-230`
- Read: `backend/app/services/artifact_binding_resolver.py`

**Step 1: 实现 input_bindings 规范化**

迁入 `_validate_standard_input_bindings()` 的行为：

```python
def _normalize_input_bindings(input_bindings: dict[str, str]) -> dict[str, str]:
    return {
        str(input_name): str(version_id)
        for input_name, version_id in (input_bindings or {}).items()
        if str(input_name).strip() and str(version_id).strip()
    }
```

**Step 2: 实现项目归属校验**

保持现有异常语义：

- 无 `project_id` 且有 ArtifactVersion 输入，抛 `ValidationException("标准 ArtifactVersion 输入绑定必须提供 project_id")`。
- ArtifactVersion 不存在或不可用，抛 `ValidationException("输入绑定引用的 ArtifactVersion 不存在", detail=...)`。
- ArtifactVersion 项目不匹配，抛 `ValidationException("输入绑定的 ArtifactVersion 必须属于任务关联项目", detail=...)`。

**Step 3: 实现 slot 绑定决策**

遍历 contract artifact inputs：

```python
contract = build_tool_contract(input.tool)
artifact_inputs = (contract.get("artifacts") or {}).get("inputs")
```

对需要 role/readiness 的 slot 调用：

```python
decision = await resolve_artifact_binding(
    db,
    input_slot=slot,
    candidate_artifact_version_id=version_id,
)
binding_decisions[slot_name] = asdict(decision)
```

**Step 4: 实现 file_ids 去重**

```python
def _dedupe_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered
```

**Step 5: 运行新增测试**

Run:

```bash
python -m pytest test/test_run_preparation.py -q
```

Expected: ArtifactVersion ready/blocked 相关测试 PASS；builtin/legacy 投影可能仍 FAIL。

## Task 4: 迁入 builtin 与 legacy SSH 投影

**Files:**
- Modify: `backend/app/services/run_preparation.py`
- Read: `backend/app/tasks/service.py:202-260`
- Read: `backend/app/services/workflow_scheduler.py:538-612`

**Step 1: 实现 `_tool_accepts_standard_input_bindings()`**

从 `workflow_scheduler.py` 迁入当前判断，保持 Tool Package v2 和 remote_api artifact inputs 行为一致。

**Step 2: 实现 builtin 投影**

规则：

```python
if executor_type == "builtin":
    params["builtin_inputs"] = {
        **existing_builtin_inputs,
        str(input_slot.get("type") or input_slot.get("name")): selected_file_id,
    }
```

**Step 3: 实现 legacy SSH 文件字段匹配**

迁入 `_legacy_file_field_for_slot()`，保留 protein/receptor、ligand、pocket、molecule table 匹配规则。

**Step 4: 实现 selected file 投影**

对不接受标准 `input_bindings` 的 legacy 工具：

```python
params["input_files"] = {
    **existing_input_files,
    file_field: f"input/{Path(file_record.filename).name}",
}
```

**Step 5: 运行新增测试**

Run:

```bash
python -m pytest test/test_run_preparation.py -q
```

Expected: 新增 `RunPreparation` 单测全部 PASS。

## Task 5: 让 Task 创建入口调用 RunPreparation

**Files:**
- Modify: `backend/app/tasks/service.py`
- Modify: `test/test_tasks_service_standard_inputs.py`

**Step 1: 写服务层兼容测试**

新增 create task 测试，断言：

- 传入 `input_bindings` 后 `task.extra_data["input_bindings"]` 保留。
- `task.extra_data["binding_decisions"]` 保留。
- `TaskInput.file_ids` 含 selected file。
- legacy SSH 的 `TaskInput.params["input_files"]` 不变。

**Step 2: 导入新模块**

```python
from app.services.run_preparation import RunContext, RunPreparationInput, prepare_run
```

**Step 3: 替换 `_project_standard_input_bindings()` 调用**

在 `create_and_schedule_tool_task()` 中构造：

```python
prepared = await prepare_run(
    db,
    input=RunPreparationInput(
        tool=tool,
        tool_version=tool_version,
        context=RunContext(
            surface="tool_detail",
            user_id=str(current_user.id),
            project_id=project_id,
        ),
        params=dict(task_data.params or {}),
        file_ids=list(task_data.file_ids or []),
        input_bindings=task_data.input_bindings,
        standard_input_uploads=task_data.standard_input_uploads,
    ),
)
```

**Step 4: 写回兼容 extra_data**

```python
if prepared.input_bindings:
    extra_data["input_bindings"] = prepared.input_bindings
if prepared.standard_input_uploads:
    extra_data["standard_input_uploads"] = prepared.standard_input_uploads
if prepared.binding_decisions:
    extra_data["binding_decisions"] = prepared.binding_decisions
```

**Step 5: 阻塞行为保持异常**

如果 `prepared.ready is False`：

```python
raise ValidationException(
    "标准 Artifact 输入尚未满足工具要求",
    detail={"binding_decisions": prepared.binding_decisions},
)
```

**Step 6: 移除本文件重复 helper**

删除或停止使用：

- `_validate_standard_input_bindings()`
- `_project_standard_input_bindings()`
- `_project_selected_file_to_legacy_params()`
- `_legacy_file_field_for_slot()`
- `_dedupe_ordered()`

**Step 7: 运行测试**

Run:

```bash
python -m pytest test/test_run_preparation.py test/test_tasks_service_standard_inputs.py test/test_task_direct_execution.py -q
```

Expected: PASS。

## Task 6: 让 Workflow 调度入口调用 RunPreparation

**Files:**
- Modify: `backend/app/services/workflow_scheduler.py`
- Modify: `test/test_workflow_scheduler.py`

**Step 1: 增加 workflow-specific 准备 helper**

在 `run_preparation.py` 增加：

```python
async def prepare_workflow_node_run(
    db: AsyncSession,
    *,
    run: Any,
    node_id: str,
    node: dict[str, Any],
    node_states: dict[str, Any],
    tool: Any,
    current_user: Any,
) -> PreparedRun:
    ...
```

该 helper 内部负责解析 workflow input、node output、artifact slot，并最终调用 `prepare_run()`。

**Step 2: 先保持 `schedule_workflow_node()` 外层状态语义不变**

保留：

- 已有 `task_id` 时返回 waiting。
- blocked 时写 `state["status"] = "blocked"`。
- 成功调度时写 `task_id`、`input_file_ids`、`input_bindings`、`params`。

**Step 3: 替换本地投影逻辑**

将以下逻辑移入 `prepare_workflow_node_run()`：

- `resolve_node_input_files()` 中 ArtifactVersion 抽取和 role 决策。
- `resolve_builtin_input_file_map()`。
- `_project_legacy_ssh_input_files()`。

第一轮可以保留这些函数为 wrapper，但 `schedule_workflow_node()` 不再直接调用多个投影函数。

**Step 4: 运行工作流调度测试**

Run:

```bash
python -m pytest test/test_workflow_scheduler.py -q
```

Expected: PASS。

**Step 5: 运行标准 Artifact 工作流验证测试**

Run:

```bash
python -m pytest test/test_workflow_validation_standard_artifacts.py test/test_standard_request_builder.py -q
```

Expected: PASS。

## Task 7: 前端兼容回归，不做权威逻辑扩张

**Files:**
- Read: `frontend/src/composables/useStandaloneNodeRun.ts`
- Read: `frontend/src/components/workflow/WorkflowNodeRunPanel.vue`
- Read: `frontend/src/workflow/preflight.ts`
- Test: `frontend/src/components/workflow/WorkflowNodeRunPanel.spec.ts`
- Test: `frontend/src/workflow/preflight.spec.ts`
- Test: `frontend/src/workflow/contract-bindings.spec.ts`

**Step 1: 不扩大前端内部字段构造**

第一阶段不新增前端权威 readiness 逻辑。

**Step 2: 运行现有前端测试**

Run:

```bash
cd frontend && npm run test -- WorkflowNodeRunPanel.spec.ts preflight.spec.ts contract-bindings.spec.ts
```

Expected: PASS。

**Step 3: 若后端响应字段变化导致失败**

只做兼容修复，不改变交互结构：

- `binding_decisions` 继续从 task 或 node state 读取。
- `input_bindings` 继续作为 task 响应字段展示。
- 前端仍不生成最终 legacy 文件路径。

## Task 8: 聚合验证与清理

**Files:**
- Modify as needed: `backend/app/services/run_preparation.py`
- Modify as needed: `backend/app/tasks/service.py`
- Modify as needed: `backend/app/services/workflow_scheduler.py`

**Step 1: 搜索重复逻辑残留**

Run:

```bash
rg -n "def _legacy_file_field_for_slot|def _tool_accepts_standard_input_bindings|def _project_standard_input_bindings|resolve_artifact_binding\(" backend/app
```

Expected: 投影 helper 主要集中在 `run_preparation.py`；`artifact_binding_resolver.py` 保留纯决策函数。

**Step 2: 运行后端聚合测试**

Run:

```bash
python -m pytest \
  test/test_run_preparation.py \
  test/test_artifact_binding_resolver.py \
  test/test_tasks_service_standard_inputs.py \
  test/test_workflow_scheduler.py \
  test/test_workflow_validation_standard_artifacts.py \
  test/test_standard_request_builder.py \
  test/test_worker_task_input_binding.py \
  -q
```

Expected: PASS。

**Step 3: 运行前端聚合测试**

Run:

```bash
cd frontend && npm run test -- WorkflowNodeRunPanel.spec.ts preflight.spec.ts contract-bindings.spec.ts
```

Expected: PASS。

**Step 4: 检查格式和空白错误**

Run:

```bash
git diff --check
```

Expected: 无输出。

## Definition of Done

- `RunPreparation` 模块存在，并通过自己的后端单元测试。
- `tasks.service` 不再直接持有标准 Artifact role/readiness 投影主逻辑。
- `workflow_scheduler` 的节点调度行为不变，但输入准备逻辑转由 `RunPreparation` 承担。
- 现有标准 Artifact、Workflow、Worker 输入绑定相关回归测试通过。
- 前端运行面板和预检测试通过。
- 无 git whitespace error。
- 没有自动提交 git 历史。
