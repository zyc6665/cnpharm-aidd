# Platform Architecture and Usability Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the current contract-driven workflow prototype into a maintainable drug discovery platform that can support team development and real researcher workflows.

**Architecture:** Keep the current FastAPI + Vue 3 stack and continue using `ToolContract` as the boundary between tools, Agent planning, workflow orchestration, and frontend rendering. Stabilize data contracts first, then split oversized workflow modules, then improve researcher-facing execution traceability and production operations.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic, pytest, Vue 3, Pinia, TypeScript, Ant Design Vue, Vite, node test.

## Execution Status (Updated 2026-06-24)

- Phase 0 completed: baseline hygiene, docs alignment, fixture restoration.
- Phase 1 completed: publish/import-time `ToolContract` validation is enforced.
- Phase 2 completed: workflow backend services split into validation/templates/runs/scheduler/artifacts modules.
- Phase 3 completed: workflow run node traceability and missing-output diagnostics are exposed to backend and frontend.
- Phase 4 completed: `/workflow` page is split into composables and focused child components; page size reduced below 700 lines.
- Phase 5 completed: stage-oriented workflow presets, workflow i18n cleanup, richer preflight diagnostics, node action shortcuts, and multi-dimensional tool palette filters are implemented.
- Phase 6 completed: production reconciliation loop, direct-recovery handoff, idempotent node scheduling, and long-run hardening are implemented.
- Phase 7 completed: Alembic baseline, development fallback policy, and SQLite migration dry run are implemented.

---

## Current Architecture Summary

The platform is a FastAPI single backend plus a Vue 3 SPA frontend. Backend APIs are registered through `backend/app/api/v1/__init__.py`, with major domains for tools, tasks, files, agents, users, system settings, and workflows.

The core drug discovery workflow path is:

`ToolVersion.config -> ToolContract -> workflow node -> WorkflowTemplate -> WorkflowRun -> Task -> File artifacts -> semantic outputs -> downstream node`

Important current modules:

- Backend entry: `backend/app/main.py`
- Tool models: `backend/app/models/tools.py`
- Workflow models: `backend/app/models/workflows.py`
- Tool contract serializer: `backend/app/services/tool_contracts.py`
- Workflow orchestration service: `backend/app/services/workflows.py`
- AIDD Agent services: `backend/app/agents/aidd/`
- Frontend workflow page: `frontend/src/views/workflow/index.vue`
- Frontend workflow store: `frontend/src/stores/workflow.ts`
- Frontend workflow domain helpers: `frontend/src/workflow/`

## Main Problems

1. `ToolContract` exists but is not yet strict enough as a publish-time platform boundary.
2. Workflow services and frontend page/store are too large and hard to maintain.
3. Workflow run traceability is not yet sufficient for drug discovery users.
4. Database schema changes still rely heavily on `create_all()` instead of formal migrations.
5. Some docs drift from implementation, such as README mentioning Element Plus while code uses Ant Design Vue.
6. Production behavior is not explicit enough around Celery/direct execution, workflow reconciliation, and long-running task recovery.

---

## Phase 0: Baseline Hygiene and Documentation Alignment

**Goal:** Make the repository clean enough for team development before further changes.

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Review: `docs/guides/团队协作开发指南.md`
- Test: `test/test_tool_import_config.py`

**Tasks:**
1. Run `git status --short --branch` and confirm only intentional source changes appear.
2. Verify ignore rules for `__pycache__/`, `.pytest_cache/`, `frontend/dist/`, logs, SQLite WAL/SHM files, local uploads, and runtime storage.
3. Update `README.md` frontend stack from Element Plus to Ant Design Vue.
4. Document that all new work should happen on `6.16` in `/data/zhouyc/cpumodel_sciminer`.
5. Restore or replace missing example fixtures required by `test/test_tool_import_config.py`.
6. Run `pytest test/test_tool_import_config.py -q`.

**Acceptance Criteria:**
- Normal test/build runs do not pollute Git status with generated files.
- README accurately describes the current stack.
- Import-config tests pass without relying on local-only files.

---

## Phase 1: Make ToolContract Enforced, Not Optional

**Goal:** Ensure newly added tools can safely participate in Agent and workflow execution without frontend-specific mapping patches.

**Files:**
- Modify: `backend/app/services/tool_contracts.py`
- Modify: `backend/app/api/v1/tools.py`
- Modify: `backend/app/schemas/tools.py`
- Modify: `tool_import_config.py`
- Modify: `frontend/src/workflow/tool-bindings.ts`
- Test: `test/test_tool_contracts.py`
- Test: `test/test_tool_import_config.py`
- Test: `frontend/test/workflow-contract-bindings.test.ts`

**Tasks:**
1. Add stricter validation for missing capability inputs, outputs, semantic types, executor type, and active version.
2. Make publish/import paths reject invalid `agent_capability` unless explicitly marked non-workflow-capable.
3. Include actionable validation errors in `GET /api/v1/tools/{tool_id}/contract`.
4. Add backend tests for invalid contracts and publish/import rejection.
5. Keep `frontend/src/workflow/tool-bindings.ts` as compatibility fallback only; add comments marking it as migration-only.
6. Run:
   - `pytest test/test_tool_contracts.py test/test_tool_import_config.py -q`
   - `cd frontend && node --test test/workflow-contract-bindings.test.ts`

**Acceptance Criteria:**
- A contract-invalid workflow tool cannot be silently published.
- Frontend, Agent, and workflow all read the same contract shape.
- Static frontend bindings are no longer required for newly imported valid tools.

---

## Phase 2: Split Workflow Backend Responsibilities

**Goal:** Reduce `backend/app/services/workflows.py` into smaller services with clear ownership.

**Files:**
- Create: `backend/app/services/workflow_validation.py`
- Create: `backend/app/services/workflow_templates.py`
- Create: `backend/app/services/workflow_runs.py`
- Create: `backend/app/services/workflow_scheduler.py`
- Create: `backend/app/services/workflow_artifacts.py`
- Modify: `backend/app/services/workflows.py`
- Modify: `backend/app/api/v1/workflows.py`
- Test: `test/test_workflow_persistence_api.py`

**Tasks:**
1. Move graph validation and topological ordering into `workflow_validation.py`.
2. Move template CRUD into `workflow_templates.py`.
3. Move run CRUD and run serialization helpers into `workflow_runs.py`.
4. Move node scheduling and task creation into `workflow_scheduler.py`.
5. Move semantic output extraction and file annotation into `workflow_artifacts.py`.
6. Keep `workflows.py` as a temporary compatibility facade, or remove it after imports are updated.
7. Run `pytest test/test_workflow_persistence_api.py -q`.

**Acceptance Criteria:**
- Each workflow service file has one clear responsibility.
- Existing workflow API behavior is unchanged.
- Workflow persistence tests pass.

---

## Phase 3: Add Workflow Node Run Traceability

**Goal:** Give researchers a reliable audit trail for every node in a workflow run.

**Files:**
- Modify: `backend/app/models/workflows.py`
- Modify: `backend/app/schemas/workflows.py`
- Modify: `backend/app/services/workflow_runs.py`
- Modify: `backend/app/services/workflow_scheduler.py`
- Modify: `backend/app/api/v1/workflows.py`
- Modify: `frontend/src/types/models.d.ts`
- Modify: `frontend/src/components/workflow/WorkflowRunStatusPanel.vue`
- Test: `test/test_workflow_persistence_api.py`
- Test: `frontend/test/workflow-run-summary.test.ts`

**Tasks:**
1. Add a node-level run record model or a typed `node_states` schema containing:
   - `node_id`
   - `tool_id`
   - `tool_slug`
   - `tool_version_id`
   - `params`
   - `input_file_ids`
   - `task_id`
   - `semantic_outputs`
   - `started_at`
   - `finished_at`
   - `error_message`
2. Ensure `create_workflow_run` stores exact tool versions and params before scheduling.
3. Ensure `sync_workflow_run` records missing semantic output details with expected type and output rule.
4. Show node input, output, task, and error details in the run status panel.
5. Run backend and frontend run-summary tests.

**Acceptance Criteria:**
- A researcher can inspect what each node used and produced.
- Failed nodes identify missing input/output semantic types clearly.
- Saved workflow runs remain reproducible at the tool-version level.

---

## Phase 4: Split Workflow Frontend Page and Store

**Goal:** Make the workflow workbench maintainable for multiple frontend developers.

**Files:**
- Create: `frontend/src/composables/useWorkflowCanvas.ts`
- Create: `frontend/src/composables/useWorkflowPersistence.ts`
- Create: `frontend/src/composables/useWorkflowExecution.ts`
- Create: `frontend/src/components/workflow/WorkflowTemplateToolbar.vue`
- Create: `frontend/src/components/workflow/WorkflowRunInputPanel.vue`
- Create: `frontend/src/components/workflow/WorkflowToolPalette.vue`
- Modify: `frontend/src/views/workflow/index.vue`
- Modify: `frontend/src/stores/workflow.ts`
- Test: existing `frontend/test/workflow-*.test.ts`

**Tasks:**
1. Move template save/load/delete/duplicate/run logic from `index.vue` into `useWorkflowPersistence.ts`.
2. Move ready-node and node-run logic into `useWorkflowExecution.ts`.
3. Move canvas node/edge add/delete/move helpers into `useWorkflowCanvas.ts`.
4. Extract template toolbar markup into `WorkflowTemplateToolbar.vue`.
5. Extract required input selection into `WorkflowRunInputPanel.vue`.
6. Extract sidebar tool list/search into `WorkflowToolPalette.vue`.
7. Keep `index.vue` as layout composition only.
8. Split `workflow.ts` store into session state and persistence/run actions if the file remains over 500 lines.
9. Run:
   - `cd frontend && node --test test/workflow-persistence-surface.test.ts test/workflow-template-page-surface.test.ts test/workflow-run-summary.test.ts`
   - `cd frontend && npm run build`

**Acceptance Criteria:**
- `frontend/src/views/workflow/index.vue` is reduced below 700 lines.
- `frontend/src/stores/workflow.ts` is reduced or split into focused stores/composables.
- Build and focused workflow tests pass.

---

## Phase 5: Researcher-Centered Workflow UX

**Goal:** Make `/workflow` understandable and useful for drug discovery users, not only developers.

**Files:**
- Modify: `frontend/src/views/workflow/index.vue`
- Modify: `frontend/src/components/workflow/WorkflowNodeInspector.vue`
- Modify: `frontend/src/components/workflow/WorkflowPreflightPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowRunStatusPanel.vue`
- Modify: `frontend/src/workflow/templates.ts`
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`
- Test: `frontend/test/workflow-layout-polish.test.ts`
- Test: `frontend/test/workflow-accessibility-polish.test.ts`

**Tasks:**
1. Replace mixed English labels in the workflow page with i18n keys.
2. Add stage-oriented template labels:
   - Protein PDB to pocket prediction
   - Pocket PDB to molecule generation
   - Protein + ligand to docking and affinity
   - Molecule generation to property prediction
3. Add clearer preflight messages:
   - missing workflow input
   - missing upstream artifact
   - invalid file extension
   - invalid semantic edge
   - invalid tool contract
4. Add node-level actions:
   - rerun node
   - rerun downstream
   - view task detail
   - view output files
5. Add tool palette filters by stage, semantic input, semantic output, and executor type.
6. Add empty states that tell the next action instead of only saying "暂无数据".
7. Run focused frontend polish and accessibility tests.

**Acceptance Criteria:**
- A non-engineering drug discovery user can understand why a workflow cannot run.
- Common AIDD workflows can be started from named templates.
- Node status, input source, output artifacts, and next action are visible.

---

## Phase 6: Production Readiness and Reconciliation

**Goal:** Make long workflow runs reliable across process restarts and queue delays.

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/tasks/direct_recovery.py`
- Create: `backend/app/services/workflow_reconciliation.py`
- Modify: `backend/app/services/workflow_scheduler.py`
- Test: `test/test_task_direct_execution.py`
- Test: `test/test_workflow_persistence_api.py`

**Tasks:**
1. Add explicit config flags for workflow reconciliation interval and max batch size.
2. Create a backend workflow reconcile loop that syncs non-terminal `WorkflowRun` records.
3. Add idempotency guards so a node cannot schedule duplicate tasks after repeated sync calls.
4. Add tests for:
   - repeated sync does not duplicate tasks
   - waiting run resumes after task success
   - failure stops downstream scheduling
5. Document production recommendation: Celery + Redis for real long-running jobs, direct only for development.

**Acceptance Criteria:**
- Workflow runs progress without manual sync as tasks finish.
- Process restart does not permanently orphan waiting workflow runs.
- Duplicate task scheduling is prevented.

---

## Phase 7: Database Migration Strategy

**Goal:** Stop relying on `create_all()` for schema evolution.

**Files:**
- Create: `alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/<revision>_workflow_contract_baseline.py`
- Modify: `backend/app/database/session.py`
- Modify: `docs/guides/团队协作开发指南.md`
- Test: migration dry run on SQLite dev database

**Tasks:**
1. Initialize Alembic for async SQLAlchemy metadata.
2. Generate baseline migration for current tables.
3. Add a policy: model changes require migration files.
4. Document commands:
   - `alembic revision --autogenerate -m "..."`
   - `alembic upgrade head`
   - `alembic downgrade -1`
5. Keep `create_all()` only as a development fallback until migrations are verified.

**Acceptance Criteria:**
- New schema fields can be added to existing databases reliably.
- Team members have one documented migration workflow.
- Production deployments do not depend on implicit table creation.

---

## Recommended Execution Order

1. Phase 0: hygiene and docs
2. Phase 1: enforced ToolContract boundary
3. Phase 2: backend workflow split
4. Phase 3: node-level run traceability
5. Phase 4: frontend workflow split
6. Phase 5: researcher UX
7. Phase 6: reconciliation
8. Phase 7: migration strategy

Phase 7 can start earlier if database changes are planned immediately. Do not add broad new workflow features before Phase 1 and Phase 2 are stable.

## Verification Commands

Use these before each commit when relevant:

```bash
pytest test/test_tool_contracts.py test/test_workflow_persistence_api.py -q
pytest test/test_aidd_agent_registry.py test/test_aidd_agent_reconcile.py -q
cd frontend && node --test test/workflow-contract-bindings.test.ts test/workflow-persistence-surface.test.ts test/workflow-run-summary.test.ts
cd frontend && npm run build
```

For full handoff after a phase:

```bash
pytest test -q
cd frontend && npm run build
```

If full frontend source-based tests fail because they encode old UI surfaces, update the tests only after confirming the expected UX has intentionally changed.

## Commit Policy

Use small commits by phase:

- `chore(repo): clean runtime artifacts and docs`
- `feat(tools): enforce workflow tool contracts`
- `refactor(workflow): split backend orchestration services`
- `feat(workflow): add node run traceability`
- `refactor(frontend): split workflow workbench modules`
- `feat(workflow): improve researcher execution guidance`
- `feat(workflow): add run reconciliation loop`
- `chore(db): add alembic migration baseline`

Each commit should include tests run in the commit message body or handoff note.
