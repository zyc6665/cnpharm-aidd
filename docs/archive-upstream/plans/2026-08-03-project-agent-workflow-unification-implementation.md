# Project Agent Workflow Unification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unify the production Agent entry around project research conversations and downgrade `/workflow` Agent mode into a project-scoped workflow draft assistant.

**Architecture:** The project research page becomes the only production Agent surface. Workflow remains a manual workbench plus a project-scoped draft generator that persists `WorkflowDefinition(status=draft, project_id=...)`. Backend workflow APIs carry project ownership explicitly and validate membership when project scope is used.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic, Vue 3, Pinia, Vitest, pytest.

---

### Task 1: Persist Project-Scoped Workflow Definitions

**Files:**
- Modify: `backend/app/schemas/workflows.py`
- Modify: `backend/app/api/v1/workflows.py`
- Test: `test/test_workflow_definitions_api.py`

**Step 1: Write failing backend tests**

Add coverage that:

- Creating a workflow definition with `project_id` returns `project_id`.
- Listing with `project_id` returns only that project’s definitions.
- A user without membership cannot create or list project-scoped definitions.

**Step 2: Verify RED**

Run:

```bash
PYTHONPATH=backend pytest test/test_workflow_definitions_api.py -q
```

Expected: failure because schemas and `/workflows` do not expose or filter `project_id`.

**Step 3: Implement minimal backend support**

- Add optional `project_id` to create, update, and response schemas.
- Import and use `load_project_membership` in workflow routes.
- Filter `GET /workflows` by `project_id` when provided.
- Validate membership before project-scoped create/update/read.

**Step 4: Verify GREEN**

Run:

```bash
PYTHONPATH=backend pytest test/test_workflow_definitions_api.py -q
```

Expected: pass.

**Step 5: Commit**

```bash
git add backend/app/schemas/workflows.py backend/app/api/v1/workflows.py test/test_workflow_definitions_api.py
git commit -m "feat(workflows): support project-scoped definitions"
```

### Task 2: Remove `/workflow` Legacy Agent Run Surface

**Files:**
- Modify: `frontend/src/components/workflow/AiddAgentPanel.vue`
- Modify: `frontend/src/api/workflows.ts`
- Modify: `frontend/src/stores/workflow-definitions.ts`
- Modify: `frontend/src/views/workflow/index.vue`
- Test: `frontend/src/views/workflow/free-workflow.spec.ts`

**Step 1: Write failing frontend tests**

Add coverage that:

- The `/workflow` Agent tab no longer exposes legacy run/history/sync/cancel UI.
- The draft-generated handler saves a `WorkflowDefinition` payload and imports it into the canvas.
- Workflow definition payloads support optional `project_id`.

**Step 2: Verify RED**

Run:

```bash
cd frontend && npm test -- src/views/workflow/free-workflow.spec.ts --run
```

Expected: failure because current panel still exposes legacy run UI and payload types do not include `project_id`.

**Step 3: Implement minimal frontend support**

- Rename the Agent panel experience to draft generation only.
- Remove direct `createRun`, history, sync, cancel, and polling UI from the workflow panel.
- Add optional `project_id` to workflow definition TypeScript payload/response types.
- Save generated drafts through `workflowDefinitionsStore.saveWorkflowDefinition`.
- Import saved draft into the canvas after save.

**Step 4: Verify GREEN**

Run:

```bash
cd frontend && npm test -- src/views/workflow/free-workflow.spec.ts --run
```

Expected: pass.

**Step 5: Commit**

```bash
git add frontend/src/components/workflow/AiddAgentPanel.vue frontend/src/api/workflows.ts frontend/src/stores/workflow-definitions.ts frontend/src/views/workflow/index.vue frontend/src/views/workflow/free-workflow.spec.ts
git commit -m "feat(workflow): downgrade agent mode to draft assistant"
```

### Task 3: Final Verification

**Files:**
- No source edits unless failures require targeted fixes.

**Step 1: Run focused backend and frontend tests**

```bash
PYTHONPATH=backend pytest test/test_workflow_definitions_api.py -q
cd frontend && npm test -- src/views/workflow/free-workflow.spec.ts --run
```

**Step 2: Run repository checks**

```bash
git diff --check
```

**Step 3: Review and commit any targeted fixes**

If verification uncovers issues, fix with TDD where behavior changes, rerun focused tests, then commit.

