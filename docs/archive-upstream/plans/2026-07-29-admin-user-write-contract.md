# Admin User Write Contract Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make every administrator user mutation return the standard response shape already declared by the frontend API client.

**Architecture:** Wrap create, update, password reset, soft delete, and hard delete results at the FastAPI route boundary while preserving domain behavior and HTTP status codes. Keep the frontend client contract unchanged and prove the runtime shape with API tests.

**Tech Stack:** FastAPI, Pydantic, async SQLAlchemy, pytest, TypeScript API declarations.

---

### Task 1: Define failing response-shape tests

**Files:**
- Modify: `test/test_admin_user_routes.py`

Add assertions for `code`, `message`, and nested `data` on create, update, reset-password, soft-delete, and hard-delete responses. Run the focused file and confirm the current naked responses fail.

### Task 2: Standardize route responses

**Files:**
- Modify: `backend/app/api/v1/users.py`

Use `success_response` for every administrator mutation, change response models where required, preserve HTTP 201 for create, and keep existing authorization/transaction behavior. Run the focused admin user tests and commit with `fix(api): standardize admin user mutations`.

### Task 3: Verify frontend and full regressions

**Files:**
- Modify only files required by verified regressions.

Run the administrator frontend surface tests, frontend build, backend F401 gate, backend full suite, and frontend full suite. Confirm only preserved local files remain in `git status`.
