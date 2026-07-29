# AIDD Workflow Draft Generation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Generate a validated, editable workflow draft from an AIDD request without creating or scheduling an agent/workflow run.

**Architecture:** Extract the side-effect-free planning preparation from the existing AIDD run service, convert its validated plan into the current workflow definition contract, and expose it through an authenticated endpoint. Resolve virtual capabilities to private platform builtin tools, then load the returned definition into the existing Vue workflow canvas for explicit user review, save, or execution.

**Tech Stack:** FastAPI, Pydantic, async SQLAlchemy, pytest, Vue 3, Pinia, TypeScript, Ant Design Vue, Node test runner, Vite.

---

### Task 1: Add the pure plan-to-workflow converter

**Files:**
- Create: `backend/app/agents/aidd/workflow_drafts.py`
- Test: `test/test_aidd_workflow_drafts.py`

**Step 1: Write failing converter tests**

Cover input nodes, tool nodes, `agent_input` and `step:` source conversion, stable edge IDs, deterministic topology positions, version traces, and invalid source rejection.

**Step 2: Run the focused test and confirm failure**

Run: `python -m pytest test/test_aidd_workflow_drafts.py -q`

Expected: FAIL because the converter module does not exist.

**Step 3: Implement the minimal pure converter**

Add a function that accepts `AIDDPlan`, semantic input IDs, and resolved tool contracts, then returns the workflow definition. Normalize semantic types and call `validate_workflow_definition` before returning.

**Step 4: Run the focused test**

Run: `python -m pytest test/test_aidd_workflow_drafts.py -q`

Expected: PASS.

**Step 5: Commit**

Run: `git add backend/app/agents/aidd/workflow_drafts.py test/test_aidd_workflow_drafts.py && git commit -m "feat(agent): convert plans to workflow drafts"`

### Task 2: Extract shared planning and expose the draft API

**Files:**
- Modify: `backend/app/agents/aidd/service.py`
- Modify: `backend/app/schemas/agent.py`
- Modify: `backend/app/api/v1/agents.py`
- Modify: `test/test_aidd_workflow_drafts.py`

**Step 1: Write failing service and API tests**

Verify authentication and file ownership, response shape, real tool/version resolution, and that row counts for agent runs, workflow templates, workflow runs, and tasks do not change.

**Step 2: Run the focused tests and confirm failure**

Run: `python -m pytest test/test_aidd_workflow_drafts.py -q`

Expected: FAIL because the service and route are missing.

**Step 3: Extract shared planning preparation**

Introduce an internal result dataclass and helper used by both `create_agent_run` and draft creation. Keep persistence and scheduling only in `create_agent_run`.

**Step 4: Add schema, service, serializer, and route**

Add `AIDDWorkflowDraftResponse`, `create_workflow_draft`, and `POST /aidd/workflow-drafts`. Resolve every planned tool to a usable persisted tool and include its current version snapshot.

**Step 5: Run focused AIDD regressions**

Run: `python -m pytest test/test_aidd_workflow_drafts.py test/test_aidd_agent_api.py test/test_aidd_langgraph_service.py -q`

Expected: PASS.

**Step 6: Commit**

Run: `git add backend/app/agents/aidd/service.py backend/app/schemas/agent.py backend/app/api/v1/agents.py test/test_aidd_workflow_drafts.py && git commit -m "feat(api): generate AIDD workflow drafts"`

### Task 3: Allow only private platform builtins in workflow execution

**Files:**
- Modify: `backend/app/services/workflow_scheduler.py`
- Modify: `test/test_workflow_scheduler.py`

**Step 1: Write failing authorization tests**

Verify a published private platform builtin tool is accepted while a published private user tool and inactive/deprecated builtin versions are rejected.

**Step 2: Run the focused test and confirm failure**

Run: `python -m pytest test/test_workflow_scheduler.py -q`

Expected: FAIL because all private tools are currently rejected.

**Step 3: Implement the narrow availability predicate**

Keep the published/current-version checks and allow `is_public=false` only when provider and executor identify a platform builtin.

**Step 4: Run workflow regressions**

Run: `python -m pytest test/test_workflow_scheduler.py test/test_workflow_runs_api.py -q`

Expected: PASS.

**Step 5: Commit**

Run: `git add backend/app/services/workflow_scheduler.py test/test_workflow_scheduler.py && git commit -m "fix(workflow): execute private platform builtins"`

### Task 4: Add frontend draft API and store state

**Files:**
- Modify: `frontend/src/types/agent.ts`
- Modify: `frontend/src/api/agents.ts`
- Modify: `frontend/src/stores/agent.ts`
- Modify: `frontend/test/aidd-agent-surface.test.ts`

**Step 1: Add failing source-contract tests**

Assert the draft type, API route, store action, independent `drafting` state, and error reset behavior exist.

**Step 2: Run the focused test and confirm failure**

Run: `npm run test -- --run test/aidd-agent-surface.test.ts`

Expected: FAIL because draft generation is absent.

**Step 3: Implement types, API, and store action**

Reuse the run request payload type where compatible and return the strongly typed draft response.

**Step 4: Run the focused test**

Run: `npm run test -- --run test/aidd-agent-surface.test.ts`

Expected: PASS.

**Step 5: Commit**

Run: `git add frontend/src/types/agent.ts frontend/src/api/agents.ts frontend/src/stores/agent.ts frontend/test/aidd-agent-surface.test.ts && git commit -m "feat(frontend): add workflow draft client"`

### Task 5: Apply generated drafts to the workflow canvas

**Files:**
- Modify: `frontend/src/components/workflow/AiddAgentPanel.vue`
- Modify: `frontend/src/views/workflow/index.vue`
- Modify: `frontend/src/views/workflow/composables/useWorkflowPersistence.ts`
- Modify: `frontend/src/locales/zh-CN.ts`
- Modify: `frontend/src/locales/en-US.ts`
- Modify: `frontend/test/aidd-agent-surface.test.ts`
- Modify: `frontend/test/workflow-template-page-surface.test.ts`

**Step 1: Add failing interaction-contract tests**

Assert the panel emits `draft-generated`, uses shared upload preparation, exposes an independent draft action, and the parent applies the definition, clears persisted-template identity, pre-fills inputs, and switches to manual mode.

**Step 2: Run the focused tests and confirm failure**

Run: `npm run test -- --run test/aidd-agent-surface.test.ts test/workflow-template-page-surface.test.ts`

Expected: FAIL because the draft UI path is absent.

**Step 3: Expose the reusable definition mapper**

Refactor the existing persisted-template mapping helper so both saved templates and generated drafts use one backend-definition-to-canvas path.

**Step 4: Implement panel and page integration**

Add the localized draft button, upload reuse, success/error feedback, event handler, canvas application, name update, input prefill, and manual-mode switch. Do not auto-save or auto-run.

**Step 5: Run focused frontend tests and build**

Run: `npm run test -- --run test/aidd-agent-surface.test.ts test/workflow-template-page-surface.test.ts && npm run build`

Expected: PASS; only documented third-party bundle warnings may remain.

**Step 6: Commit**

Run: `git add frontend/src/components/workflow/AiddAgentPanel.vue frontend/src/views/workflow/index.vue frontend/src/views/workflow/composables/useWorkflowPersistence.ts frontend/src/locales/zh-CN.ts frontend/src/locales/en-US.ts frontend/test && git commit -m "feat(workflow): load agent-generated drafts"`

### Task 6: Complete regression verification

**Files:**
- Modify only files required by verified regressions.

**Step 1: Run backend quality gates**

Run: `python -m flake8 backend/app --select F401`

Run: `python -m pytest test/ -q`

Expected: PASS.

**Step 2: Run frontend quality gates**

Run: `npm run test -- --run`

Run: `npm run build`

Expected: PASS.

**Step 3: Inspect repository state**

Run: `git status --short --branch`

Expected: only explicitly preserved local untracked files remain.

**Step 4: Commit any focused regression fix**

Commit only when verification required a scoped source/test correction. Do not stage local configuration, caches, databases, uploads, or the user's diagnostic checklist.
