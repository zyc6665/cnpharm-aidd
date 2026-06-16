# Workflow Canvas Persistence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add editable workflow node positions, backend persistence for workflow definitions, frontend save/load support, and a basic run-ready-nodes action.

**Architecture:** Add a small FastAPI CRUD surface backed by a `WorkflowDefinition` SQLAlchemy model. Keep workflow execution frontend-orchestrated for this phase by reusing existing task creation APIs. Extend the existing template canvas store and components rather than introducing a new graph library.

**Tech Stack:** FastAPI, SQLAlchemy Async, Pydantic, Vue 3, Pinia, Ant Design Vue, TypeScript, Node `node:test`, pytest.

---

## Task 1: Backend Workflow Definition Model And Schemas

**Files:**
- Create: `backend/app/models/workflows.py`
- Create: `backend/app/schemas/workflows.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/database/session.py`
- Test: `test/test_workflow_definitions_models.py`

Implement `WorkflowDefinition` and Pydantic create/update/response schemas.

## Task 2: Backend Workflows API

**Files:**
- Create: `backend/app/api/v1/workflows.py`
- Modify: `backend/app/api/v1/__init__.py`
- Test: `test/test_workflow_definitions_api.py`

Implement list/create/detail/update/delete for authenticated users.

## Task 3: Frontend Workflow Definition API And Store

**Files:**
- Create: `frontend/src/api/workflows.ts`
- Modify: `frontend/src/api/index.ts`
- Create: `frontend/src/stores/workflow-definitions.ts`
- Modify: `frontend/src/stores/index.ts`
- Test: `frontend/test/workflow-definitions-api-store.test.ts`

Add typed API wrappers and Pinia store for workflow definitions.

## Task 4: Draggable Canvas Positions

**Files:**
- Modify: `frontend/src/stores/workflow.ts`
- Modify: `frontend/src/components/workflow/WorkflowCanvasNode.vue`
- Modify: `frontend/src/components/workflow/WorkflowTemplateCanvas.vue`
- Test: `frontend/test/workflow-template-dragging.test.ts`

Support node position overrides and `move-node` events.

## Task 5: Save And Load From Workflow Page

**Files:**
- Modify: `frontend/src/views/workflow/index.vue`
- Test: `frontend/test/workflow-save-load-surface.test.ts`

Add save, load, and save-as controls.

## Task 6: Basic Run Ready Nodes

**Files:**
- Modify: `frontend/src/views/workflow/index.vue`
- Create: `frontend/src/workflow/template-runner.ts`
- Test: `frontend/test/workflow-run-ready-nodes.test.ts`

Add a helper that selects ready tool nodes in template order and wire it to a page action.

## Final Verification

Run:

```bash
pytest test/test_workflow_definitions_models.py test/test_workflow_definitions_api.py
cd frontend
node --test test/workflow-definitions-api-store.test.ts test/workflow-template-dragging.test.ts test/workflow-save-load-surface.test.ts test/workflow-run-ready-nodes.test.ts
npm run build
```
