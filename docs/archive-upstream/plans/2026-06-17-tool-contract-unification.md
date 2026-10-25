# Tool Contract Unification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Centralize platform tool field mapping behind a backend `ToolContract`.

**Architecture:** Add a pure serializer in `backend/app/services/tool_contracts.py`, adapt `backend/app/agents/aidd/registry.py` to produce Agent summaries from normalized contracts while keeping existing planner fields, and enforce Agent capability consistency in `tool_import_config.py`.

**Tech Stack:** FastAPI backend, SQLAlchemy ORM models, Pydantic-compatible dict contracts, pytest.

---

### Task 1: Contract Serializer

**Files:**
- Create: `backend/app/services/tool_contracts.py`
- Test: `test/test_tool_contracts.py`

**Steps:**
1. Write a failing test for `build_tool_contract`.
2. Run `pytest test/test_tool_contracts.py -q` and confirm import failure.
3. Implement the serializer.
4. Re-run the test and confirm it passes.

### Task 2: Agent Summary Integration

**Files:**
- Modify: `backend/app/agents/aidd/registry.py`
- Test: `test/test_tool_contracts.py`

**Steps:**
1. Write a failing test proving Agent summaries include stable `slug` plus legacy `tool_slug`.
2. Update registry summary generation to use contracts.
3. Re-run focused tests.

### Task 3: Verification

**Steps:**
1. Run `pytest test/test_tool_contracts.py test/test_aidd_agent_registry.py -q`.
2. Run the broader AIDD registry/payload tests if needed.

### Task 4: Import-Time Capability Validation

**Files:**
- Modify: `tool_import_config.py`
- Test: `test/test_tool_import_config.py`

**Steps:**
1. Add failing tests for valid capability config, missing input field, and unknown semantic type.
2. Add supported Agent semantic type and output source constants.
3. Validate `agent_capability.inputs`, `outputs`, and `defaults` against `input_schema`.
4. Run focused import-config tests and AIDD regression tests.
