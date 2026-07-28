# AIDD Unified Task Execution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move every executable AIDD step onto the platform task system while closing cancellation, concurrency, validation, capability-discovery, and history-pagination gaps.

**Architecture:** Persisted platform tools with `type: builtin` will represent the currently supported AIDD internal capabilities. A `BuiltinExecutor` will run in the existing worker/direct-runner path and emit standard `TaskOutput` artifacts. The AIDD service will only schedule and reconcile tasks, claiming steps atomically before dispatch.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Celery/direct runner, Pydantic, pytest, Vue 3/Pinia.

---

### Task 1: Define supported built-in capability catalog

**Files:**
- Modify: `backend/app/agents/aidd/capabilities.py`
- Modify: `backend/app/agents/aidd/builtin_tools.py`
- Test: `test/test_aidd_builtin_tools.py`
- Test: `test/test_aidd_agent_registry.py`

**Step 1: Write failing tests**

```python
def test_placeholder_scientific_capabilities_are_not_agent_available():
    assert "builtin-admet-prediction" not in supported_builtin_tool_slugs()
```

**Step 2: Run test to verify it fails**

Run: `pytest -q test/test_aidd_builtin_tools.py -k placeholder`

**Step 3: Implement minimal catalog change**

- Expose only SDF conversion, Vina, and database-query built-ins as supported.
- Remove placeholder ADMET, toxicity, SA, MD, and interaction handlers from the executable registry.
- Retain explicit `ValidationException` for attempts to execute retired slugs.

**Step 4: Run focused tests**

Run: `pytest -q test/test_aidd_builtin_tools.py test/test_aidd_agent_registry.py`

### Task 2: Persist platform tools for supported built-ins

**Files:**
- Create: `backend/app/services/aidd_builtin_tools.py`
- Create: `backend/alembic/versions/20260728_01_aidd_builtin_tools.py`
- Modify: `backend/app/models/tools.py` only if enum validation requires `builtin`
- Test: `test/test_aidd_builtin_task_tools.py`

**Step 1: Write failing tests**

```python
async def test_ensure_aidd_builtin_tools_creates_published_builtin_tool(db_session, admin):
    tool = await ensure_aidd_builtin_tool(db_session, admin, "builtin-vina-docking")
    assert tool.current_version.config["type"] == "builtin"
```

**Step 2: Run test to verify it fails**

Run: `pytest -q test/test_aidd_builtin_task_tools.py::test_ensure_aidd_builtin_tools_creates_published_builtin_tool`

**Step 3: Implement minimal persistence layer**

- Define immutable metadata for each supported built-in slug and its capability contract.
- Create idempotent service logic and an Alembic data migration to create published `Tool`/`ToolVersion` records with `type: builtin`.
- Resolve the system owner from `AIDD_SYSTEM_USER_ID`; fail configuration validation if the configured user does not exist.

**Step 4: Run focused tests**

Run: `pytest -q test/test_aidd_builtin_task_tools.py`

### Task 3: Execute built-ins through TaskExecutor

**Files:**
- Modify: `backend/app/tasks/executor.py`
- Modify: `backend/app/agents/aidd/builtin_tools.py`
- Test: `test/test_aidd_builtin_task_executor.py`

**Step 1: Write failing tests**

```python
async def test_builtin_executor_persists_vina_artifacts_as_task_outputs(...):
    result = await BuiltinExecutor(task, tool_version).execute()
    assert result["output_file_ids"]
```

**Step 2: Run test to verify it fails**

Run: `pytest -q test/test_aidd_builtin_task_executor.py -k persists`

**Step 3: Implement minimal executor**

- Add `BuiltinExecutor` to `TaskExecutor.EXECUTORS`.
- Make built-in dispatch async; run blocking subprocess work with `asyncio.to_thread` and await database-query clients directly.
- Materialize artifacts via the standard executor output collection path and return `TaskOutput`-compatible result data.
- Read the requested built-in slug from trusted tool-version config, not user parameters.

**Step 4: Run focused tests**

Run: `pytest -q test/test_aidd_builtin_task_executor.py test/test_aidd_builtin_tools.py`

### Task 4: Make all AIDD steps task-backed and cancellable

**Files:**
- Modify: `backend/app/agents/aidd/service.py`
- Create: `backend/app/tasks/cancellation.py`
- Modify: `backend/app/api/v1/tasks.py`
- Test: `test/test_aidd_agent_api.py`
- Test: `test/test_aidd_agent_cancellation.py`

**Step 1: Write failing tests**

```python
async def test_cancel_agent_run_cancels_waiting_platform_task(...):
    run = await create_waiting_agent_run(...)
    await cancel_agent_run(...)
    assert task.status == TaskStatus.CANCELED.value
```

**Step 2: Run test to verify it fails**

Run: `pytest -q test/test_aidd_agent_cancellation.py`

**Step 3: Implement minimal scheduling and cancellation changes**

- Delete the direct virtual-step execution path from AIDD service.
- Resolve supported built-ins to their persisted platform tools before `create_and_schedule_tool_task`.
- Extract task cancellation from the API route into a reusable service, including direct runner and Celery revoke behavior.
- Cancel linked pending/running tasks before marking AIDD steps and run canceled.

**Step 4: Run focused tests**

Run: `pytest -q test/test_aidd_agent_api.py test/test_aidd_agent_cancellation.py`

### Task 5: Claim ready steps atomically

**Files:**
- Modify: `backend/app/agents/aidd/service.py`
- Modify: `backend/app/models/agent.py`
- Create: `backend/alembic/versions/20260728_02_agent_step_dispatch_guards.py`
- Test: `test/test_aidd_agent_concurrency.py`

**Step 1: Write failing test**

```python
async def test_two_reconcilers_create_one_downstream_task(...):
    await asyncio.gather(reconcile_one(), reconcile_two())
    assert await count_tasks_for_step(step.id) == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest -q test/test_aidd_agent_concurrency.py`

**Step 3: Implement minimal atomic claim**

- Add a unique relationship between an agent step and its dispatched task where supported by the schema.
- Use a conditional `UPDATE ... WHERE status IN ('pending', 'ready')` before creating a task.
- Re-read claimed state before reconciliation transitions; use row locking where available for dependent-state updates.

**Step 4: Run focused tests**

Run: `pytest -q test/test_aidd_agent_concurrency.py test/test_aidd_agent_background.py`

### Task 6: Validate plans before persistence

**Files:**
- Modify: `backend/app/agents/aidd/plan_schema.py`
- Modify: `backend/app/agents/aidd/graph.py`
- Test: `test/test_aidd_plan_preflight.py`

**Step 1: Write failing tests**

```python
def test_plan_rejects_missing_required_capability_input():
    with pytest.raises(PlanValidationError, match="ligand_pdb"):
        parse_model_plan(...)
```

**Step 2: Run test to verify it fails**

Run: `pytest -q test/test_aidd_plan_preflight.py`

**Step 3: Implement minimal preflight**

- Check required input semantic types against uploaded inputs and declared upstream outputs.
- Validate every `step:` reference and reject unavailable/retired built-ins.
- Keep the current acyclic dependency and tool-capability checks.

**Step 4: Run focused tests**

Run: `pytest -q test/test_aidd_plan_preflight.py test/test_aidd_langgraph_service.py`

### Task 7: Resolve capabilities per tool

**Files:**
- Modify: `backend/app/agents/aidd/registry.py`
- Test: `test/test_aidd_dynamic_capabilities.py`
- Test: `test/test_aidd_agent_registry.py`

**Step 1: Write failing test**

```python
async def test_db_capability_does_not_hide_other_config_capability(...):
    summaries = await load_available_tool_summaries(db_session)
    assert {"db-tool", "config-tool"} <= {item["slug"] for item in summaries}
```

**Step 2: Run test to verify it fails**

Run: `pytest -q test/test_aidd_dynamic_capabilities.py -k does_not_hide`

**Step 3: Implement minimal merge**

- Load published tools once with current versions.
- Resolve DB capability for each tool, then config capability, then static fallback.
- Build summaries from the loaded tool objects to avoid N+1 queries.

**Step 4: Run focused tests**

Run: `pytest -q test/test_aidd_dynamic_capabilities.py test/test_aidd_agent_registry.py`

### Task 8: Add paginated agent history and cancellation control

**Files:**
- Modify: `backend/app/api/v1/agents.py`
- Modify: `backend/app/agents/aidd/service.py`
- Modify: `frontend/src/api/agents.ts`
- Modify: `frontend/src/stores/agents.ts`
- Modify: `frontend/src/components/workflow/AiddAgentPanel.vue`
- Test: `test/test_aidd_agent_api.py`
- Test: `frontend/test/aidd-agent-history.test.ts`

**Step 1: Write failing tests**

```python
async def test_list_agent_runs_honors_page_and_page_size(...):
    response = await client.get("/api/v1/agents/aidd/runs?page=2&page_size=2")
    assert response.json()["data"]["page"] == 2
```

**Step 2: Run test to verify it fails**

Run: `pytest -q test/test_aidd_agent_api.py -k page`

**Step 3: Implement minimal API and UI behavior**

- Add bounded page and page-size query parameters and total query.
- Fetch only requested history in the Pinia store.
- Show a cancel control only for nonterminal runs and stop polling after cancellation.

**Step 4: Run focused tests**

Run: `pytest -q test/test_aidd_agent_api.py && npm test -- --run frontend/test/aidd-agent-history.test.ts`

### Task 9: Run complete verification and prepare versioned commits

**Files:**
- Modify: files from Tasks 1-8 only

**Step 1: Run backend suite**

Run: `pytest test`

**Step 2: Run frontend verification**

Run: `npm test && npm run build` from `frontend/`

**Step 3: Inspect migration and working-tree state**

Run: `git diff --check && git status --short`

**Step 4: Commit cohesive batches**

```bash
git add backend test docs/plans
git commit -m "feat(aidd): unify agent steps with task execution"
git add frontend
git commit -m "feat(frontend): add agent history controls"
```
