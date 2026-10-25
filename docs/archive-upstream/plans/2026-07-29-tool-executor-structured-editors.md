# Tool Executor Structured Editors Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace raw JSON and whitespace-delimited executor configuration fields with structured editors whose saved values are honored by runtime executors.

**Architecture:** Add pure conversion helpers and two reusable unframed Vue editors, then make `Create.vue` use arrays of rows as the single source of truth for executor maps and lists. Preserve the existing backend config object/array contract and update the Python executor to pass validated configured arguments directly to subprocess.

**Tech Stack:** Vue 3, TypeScript, Ant Design Vue, Vitest, FastAPI backend domain code, pytest, asyncio subprocess execution.

---

### Task 1: Add structured editor conversion helpers

**Files:**
- Create: `frontend/src/utils/tool-config-editors.ts`
- Create: `frontend/test/tool-config-editors.test.ts`

**Steps:**
1. Write failing tests for object round-trip, empty-row filtering, duplicate-key rejection, array item preservation, and legacy string normalization.
2. Run `npm run test -- --run test/tool-config-editors.test.ts` and confirm missing-module failure.
3. Implement the minimal typed helpers.
4. Re-run the focused test and confirm PASS.
5. Commit with `feat(frontend): add tool config editor helpers`.

### Task 2: Add reusable structured editor components

**Files:**
- Create: `frontend/src/components/tools/StructuredKeyValueEditor.vue`
- Create: `frontend/src/components/tools/StructuredStringListEditor.vue`
- Modify: `frontend/test/tool-create-page-polish.test.ts`

**Steps:**
1. Add failing source-contract tests for stable rows, add/remove actions, icon buttons, aria labels, and mobile layout.
2. Run the focused test and confirm failure.
3. Implement both controlled components with immutable emits.
4. Run focused tests and `npm run build`.
5. Commit with `feat(frontend): add structured config editors`.

### Task 3: Refactor tool creation executor fields

**Files:**
- Modify: `frontend/src/views/tools/Create.vue`
- Modify: `frontend/test/tool-create-page-polish.test.ts`
- Modify: `test/test_admin_tool_category_frontend_surface.py`

**Steps:**
1. Add failing tests requiring structured components for API headers, Docker/SSH env, Docker command, Python args, and SSH globs; reject the old JSON text refs.
2. Confirm focused test failure.
3. Replace text refs with typed row/list state and shared converters.
4. Update old-config parsing, duplicate-key validation, and config serialization.
5. Run focused frontend/Python surface tests and production build.
6. Commit with `refactor(frontend): structure executor configuration`.

### Task 4: Honor Python script arguments at runtime

**Files:**
- Modify: `backend/app/tasks/executors/python_script.py`
- Modify: `test/test_python_script_executor_security.py`

**Steps:**
1. Write failing tests that capture the subprocess command and verify configured arguments, embedded spaces, mandatory platform flags, and invalid argument rejection.
2. Run the focused test and confirm failure.
3. Add a small argument validation helper and insert arguments into the subprocess array without shell evaluation.
4. Run Python executor and executor-module regressions.
5. Commit with `fix(tasks): honor Python tool arguments`.

### Task 5: Complete regression verification

**Files:**
- Modify only files required by verified regressions.

**Steps:**
1. Run `python -m flake8 backend/app --select F401`.
2. Run `python -m pytest test/ -q`.
3. Run `npm run test -- --run`.
4. Run `npm run build`.
5. Confirm `git status --short --branch` contains only preserved local files.
