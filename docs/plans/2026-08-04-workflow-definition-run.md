# Workflow Definition Run Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the legacy `WorkflowTemplate -> WorkflowRun` execution path with `WorkflowDefinition -> WorkflowRun`, including project-scoped runs and frontend strict project mode.

**Architecture:** `WorkflowDefinition` becomes the only runnable workflow source. `WorkflowRun` stores a snapshot of the selected definition, inherits `project_id`, and schedules node tasks through the existing workflow scheduler. The frontend always saves the current definition before running and no longer directly creates workflow node tasks.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Alembic, Pytest, Vue 3, Pinia, Vitest, TypeScript.

---

### Task 1: Backend Definition-Run API

**Files:**
- Modify: `backend/app/models/workflows.py`
- Modify: `backend/app/schemas/workflows.py`
- Modify: `backend/app/api/v1/workflows.py`
- Modify: `backend/app/services/workflow_runs.py`
- Modify: `backend/app/services/workflow_scheduler.py`
- Test: `test/test_workflow_persistence_api.py`

**Step 1: Write failing backend API tests**

Add tests that create a `WorkflowDefinition`, then call:

```python
response = await client.post(f"/api/v1/workflows/{workflow_id}/runs", json={"input_files": {}})
```

Assert:
- response is 200
- returned run has `workflow_definition_id == workflow_id`
- returned run inherits `project_id` from the definition
- scheduled task params use `workflow_definition_id`, not `workflow_template_id`
- non-members cannot create/list/read/sync project workflow runs
- `/api/v1/workflows/templates` returns 404

**Step 2: Run tests to verify red**

Run:

```bash
PYTHONPATH=backend pytest test/test_workflow_persistence_api.py -q
```

Expected: FAIL because `POST /workflows/{workflow_id}/runs` and `workflow_definition_id` behavior do not exist yet.

**Step 3: Implement minimal backend model and API changes**

- Remove `WorkflowTemplate` from the route layer.
- Change `WorkflowRun` to reference `workflow_definition_id`.
- Create `load_definition_for_run()` that checks owner and project membership.
- Change `create_workflow_run()` to load `WorkflowDefinition`, copy its current snapshot, inherit `project_id`, and schedule ready nodes.
- Change run listing filters from `template_id` to `workflow_definition_id` and `project_id`.
- Keep scheduler internals but update task metadata from `workflow_template_id` to `workflow_definition_id`.

**Step 4: Run backend tests**

Run:

```bash
PYTHONPATH=backend pytest test/test_workflow_persistence_api.py test/test_workflow_definitions_api.py -q
python -m py_compile backend/app/api/v1/workflows.py backend/app/services/workflow_runs.py backend/app/services/workflow_scheduler.py
```

Expected: PASS.

**Step 5: Review and commit**

Run:

```bash
git diff --check
git diff --stat
git commit -m "feat(workflows): run workflow definitions"
```

---

### Task 2: Alembic Cleanup Migration

**Files:**
- Create: `backend/alembic/versions/20260804_01_workflow_definition_runs.py`
- Modify: `test/test_alembic_migration_dry_run.py`

**Step 1: Write failing migration test**

Update migration dry-run expectations:
- `workflow_templates` is no longer required in the current model.
- `workflow_runs.workflow_definition_id` is required.
- `workflow_runs.template_id` is not expected.

**Step 2: Run test to verify red**

Run:

```bash
PYTHONPATH=backend pytest test/test_alembic_migration_dry_run.py -q
```

Expected: FAIL until migration/model metadata align.

**Step 3: Add destructive migration**

Migration logic:

```python
op.execute("DELETE FROM workflow_runs")
op.add_column("workflow_runs", sa.Column("workflow_definition_id", sa.String(length=36), nullable=False))
op.create_index("ix_workflow_runs_workflow_definition_id", "workflow_runs", ["workflow_definition_id"])
op.create_foreign_key(..., "workflow_runs", "workflow_definitions", ["workflow_definition_id"], ["id"])
op.drop_constraint(... template fk ...)
op.drop_index("ix_workflow_runs_template_id", table_name="workflow_runs")
op.drop_column("workflow_runs", "template_id")
op.drop_table("workflow_templates")
```

Use inspector-safe constraint names from existing migrations where possible.

**Step 4: Run migration tests**

Run:

```bash
PYTHONPATH=backend pytest test/test_alembic_migration_dry_run.py -q
```

Expected: PASS.

**Step 5: Review and commit**

Run:

```bash
git diff --check
git commit -m "chore(db): drop workflow templates"
```

---

### Task 3: Frontend API and Stores

**Files:**
- Modify: `frontend/src/api/workflows.ts`
- Modify: `frontend/src/types/models.d.ts`
- Modify: `frontend/src/stores/workflow-runs.ts`
- Modify: `frontend/src/stores/workflow.ts`
- Modify: `frontend/src/stores/workflow-templates.ts`
- Test: `frontend/src/views/workflow/free-workflow.spec.ts`

**Step 1: Write failing frontend tests**

Extend workflow tests so `/workflow?project_id=project-1` verifies:
- `getWorkflowDefinitions` is called with `{ project_id: "project-1" }`
- save calls `createWorkflowDefinition` with `project_id`
- run calls `createWorkflowRun(workflowDefinitionId, ...)`
- run history calls `getWorkflowRuns({ project_id: "project-1" })`
- no template API is called

**Step 2: Run tests to verify red**

Run:

```bash
npm test -- src/views/workflow/free-workflow.spec.ts
```

Expected: FAIL because the page ignores route project context and still exposes template-backed helpers.

**Step 3: Implement frontend API/store change**

- Remove `WorkflowTemplate*` types and API calls.
- Change `createWorkflowRun(workflowId, payload)` to call `POST /workflows/{workflowId}/runs`.
- Add `workflow_definition_id` and `project_id` to run list params.
- Remove template store usage from the workflow facade or leave only non-exposed cleanup stubs if needed for incremental compile.

**Step 4: Run frontend tests**

Run:

```bash
npm test -- src/views/workflow/free-workflow.spec.ts
```

Expected: PASS.

**Step 5: Review and commit**

Run:

```bash
git diff --check
git commit -m "feat(frontend): use definition workflow runs"
```

---

### Task 4: Workflow Page Strict Project Mode

**Files:**
- Modify: `frontend/src/views/workflow/index.vue`
- Modify: `frontend/src/composables/useWorkflowPersistence.ts`
- Modify: `frontend/src/composables/useWorkflowExecution.ts`
- Test: `frontend/src/views/workflow/free-workflow.spec.ts`

**Step 1: Write failing behavior tests**

Add tests for:
- strict project mode visual label when `project_id` query exists
- new workflow keeps current `project_id`
- duplicate workflow keeps current `project_id`
- run button auto-saves before creating a run
- direct node task creation is not called

**Step 2: Run tests to verify red**

Run:

```bash
npm test -- src/views/workflow/free-workflow.spec.ts
```

Expected: FAIL until project context and run replacement are wired.

**Step 3: Implement page/composable changes**

- Read `project_id` from `useRoute()`.
- Pass `currentProjectId` into persistence and execution composables.
- Build definition payloads with `project_id`.
- Replace “运行可执行节点” with a standard run action that:
  1. saves or updates `WorkflowDefinition`
  2. creates a `WorkflowRun`
  3. sets active run and starts sync polling
- Remove direct `tasksStore.createTask()` workflow execution path.

**Step 4: Run frontend tests and build**

Run:

```bash
npm test -- src/views/workflow/free-workflow.spec.ts src/views/projects/Overview.spec.ts
npm run build
```

Expected: PASS; existing Vite chunk/eval warnings are acceptable if unchanged.

**Step 5: Review and commit**

Run:

```bash
git diff --check
git commit -m "feat(workflow): enforce project run context"
```

---

### Task 5: Remove Template Residue

**Files:**
- Delete: `frontend/src/stores/workflow-templates.ts`
- Modify: `frontend/src/stores/index.ts`
- Modify: `backend/app/services/workflow_templates.py`
- Modify: `backend/app/api/v1/projects.py`
- Modify: `backend/app/services/project_migration.py`
- Modify: `backend/app/api/v1/users.py`
- Modify: `test/test_projects_api.py`
- Modify: `test/test_project_backfill.py`

**Step 1: Search residue**

Run:

```bash
rg "WorkflowTemplate|workflow_templates|template_id|/workflows/templates|workflow_template_id"
```

Expected: Only acceptable remaining references are `WorkflowDefinition.template_id` if still used as a canvas mode identifier, and docs/changelog references.

**Step 2: Remove code residue**

- Delete unused backend service files and route imports.
- Remove project/user cascade deletes for `WorkflowTemplate`.
- Keep `WorkflowDefinition.template_id` only if needed as a canvas/source identifier; do not use it for execution.
- Remove frontend template store exports.

**Step 3: Run residue search again**

Run:

```bash
rg "WorkflowTemplate|workflow_templates|/workflows/templates|workflow_template_id"
```

Expected: No runtime references.

**Step 4: Run targeted regression**

Run:

```bash
PYTHONPATH=backend pytest test/test_projects_api.py test/test_project_backfill.py test/test_workflow_persistence_api.py -q
npm test -- src/views/workflow/free-workflow.spec.ts src/views/projects/Overview.spec.ts
```

Expected: PASS.

**Step 5: Review and commit**

Run:

```bash
git diff --check
git commit -m "refactor(workflows): remove template runtime"
```

---

### Task 6: Final Verification

**Files:**
- No code changes unless verification reveals a defect.

**Step 1: Full targeted backend verification**

Run:

```bash
PYTHONPATH=backend pytest test/test_workflow_persistence_api.py test/test_workflow_definitions_api.py test/test_projects_api.py test/test_workspace_overview_api.py test/test_alembic_migration_dry_run.py -q
```

Expected: PASS.

**Step 2: Frontend verification**

Run:

```bash
npm test -- src/views/workflow/free-workflow.spec.ts src/views/projects/Overview.spec.ts src/components/projects/ProjectList.spec.ts src/views/workspace/index.spec.ts src/views/workspace/project-workspace.spec.ts
npm run build
```

Expected: PASS; existing Vite warnings may remain.

**Step 3: Final review**

Run:

```bash
git status --short
git log -6 --oneline
rg "WorkflowTemplate|workflow_templates|/workflows/templates|workflow_template_id"
```

Expected: worktree clean after final commits; no runtime template references.
