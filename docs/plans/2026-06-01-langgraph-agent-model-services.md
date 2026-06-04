# LangGraph Agent Model Services Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the AIDD Agent to a LangGraph-based orchestrator and add administrator-managed OpenAI-compatible model service settings.

**Architecture:** Keep the existing tool, task, file, and agent run persistence layers. Add encrypted model service settings under the system admin API, then replace the deterministic planner entrypoint with a LangGraph state graph that plans, validates, executes, observes, and resumes through the existing task system.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, cryptography/Fernet, httpx, LangGraph, OpenAI-compatible chat completions, Vue 3, Pinia, Ant Design Vue, pytest, Node test runner.

**Project Constraint:** Do not run git commit unless the user explicitly asks. This plan intentionally omits commit steps.

---

## References

- Design doc: `docs/plans/2026-06-01-langgraph-agent-model-services-design.md`
- Current Agent API: `backend/app/api/v1/agents.py`
- Current Agent service: `backend/app/agents/aidd/service.py`
- Current planner: `backend/app/agents/aidd/planner.py`
- Current capabilities: `backend/app/agents/aidd/capabilities.py`
- Current system API: `backend/app/api/v1/system.py`
- Current admin system page: `frontend/src/views/admin/System.vue`
- Current system API client: `frontend/src/api/system.ts`
- Current frontend model types: `frontend/src/types/models.d.ts`
- Current Agent panel: `frontend/src/components/workflow/AiddAgentPanel.vue`

---

### Task 1: Add Dependency Surface Tests

**Files:**
- Modify: `backend/requirements.txt`
- Test: `test/test_langgraph_dependency_surface.py`

**Step 1: Write failing tests**

Create `test/test_langgraph_dependency_surface.py`:

```python
from pathlib import Path


def test_backend_declares_langgraph_and_secret_dependencies():
    requirements = Path("backend/requirements.txt").read_text()

    assert "langgraph" in requirements
    assert "cryptography" in requirements
```

**Step 2: Run test to verify failure**

Run: `pytest "test/test_langgraph_dependency_surface.py" -q`

Expected: FAIL because dependencies are not declared.

**Step 3: Add dependencies**

Modify `backend/requirements.txt`:

```text
langgraph==0.2.74
cryptography==42.0.8
```

Use versions compatible with the environment. If install resolution fails, adjust versions and document the reason in the final verification.

**Step 4: Verify**

Run: `pytest "test/test_langgraph_dependency_surface.py" -q`

Expected: PASS.

---

### Task 2: Add Model Service Persistence

**Files:**
- Create: `backend/app/models/system_settings.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/database/session.py`
- Create: `backend/scripts/create_model_services.sql`
- Test: `test/test_model_service_models.py`

**Step 1: Write failing model test**

Create `test/test_model_service_models.py`:

```python
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base
from app.models import system_settings as _system_settings  # noqa: F401


@pytest.mark.asyncio
async def test_model_services_table_is_registered():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        table_names = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))

    await engine.dispose()

    assert "model_services" in table_names
```

**Step 2: Run failing test**

Run: `pytest "test/test_model_service_models.py" -q`

Expected: FAIL because the model does not exist.

**Step 3: Add model**

Create `backend/app/models/system_settings.py`:

```python
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from app.database.base import Base, TimestampMixin, UUIDMixin


class ModelService(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "model_services"

    name = Column(String(100), nullable=False)
    provider_type = Column(String(50), nullable=False, default="openai_compatible")
    base_url = Column(String(500), nullable=False)
    api_key_encrypted = Column(Text, nullable=True)
    model_name = Column(String(200), nullable=False)
    is_default = Column(Boolean, nullable=False, default=False, index=True)
    is_enabled = Column(Boolean, nullable=False, default=True, index=True)
    timeout_seconds = Column(Integer, nullable=False, default=60)
    max_tokens = Column(Integer, nullable=False, default=2048)
    temperature = Column(Float, nullable=False, default=0.2)
    last_test_status = Column(String(32), nullable=True)
    last_test_message = Column(Text, nullable=True)
    last_tested_at = Column(DateTime, nullable=True)
```

Modify `backend/app/models/__init__.py` to import/export `ModelService`.

Modify `backend/app/database/session.py` so model metadata is imported during init.

Create `backend/scripts/create_model_services.sql` with SQLite-compatible schema.

**Step 4: Verify**

Run: `pytest "test/test_model_service_models.py" -q`

Expected: PASS.

---

### Task 3: Add Secret Encryption Utility

**Files:**
- Modify: `backend/app/config.py`
- Create: `backend/app/common/secret_crypto.py`
- Test: `test/test_secret_crypto.py`

**Step 1: Write failing tests**

Create `test/test_secret_crypto.py`:

```python
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common.secret_crypto import decrypt_secret, encrypt_secret, mask_secret


def test_secret_round_trip():
    encrypted = encrypt_secret("sk-test-secret")

    assert encrypted != "sk-test-secret"
    assert decrypt_secret(encrypted) == "sk-test-secret"


def test_secret_masking():
    assert mask_secret(None) is None
    assert mask_secret("sk-1234567890") == "sk-****7890"
```

**Step 2: Run failing test**

Run: `pytest "test/test_secret_crypto.py" -q`

Expected: FAIL because the module does not exist.

**Step 3: Implement utility**

Add `SETTINGS_ENCRYPTION_KEY: Optional[str] = None` to `backend/app/config.py`.

Create `backend/app/common/secret_crypto.py`:

```python
import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet

from app.config import settings


def _fernet() -> Fernet:
    raw_key = settings.SETTINGS_ENCRYPTION_KEY or settings.JWT_SECRET_KEY
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def mask_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if len(value) <= 8:
        return "****"
    return f"{value[:3]}****{value[-4:]}"
```

**Step 4: Verify**

Run: `pytest "test/test_secret_crypto.py" -q`

Expected: PASS.

---

### Task 4: Add Model Service Schemas And Service Layer

**Files:**
- Create: `backend/app/schemas/system_settings.py`
- Create: `backend/app/services/model_services.py`
- Modify: `backend/app/schemas/__init__.py`
- Test: `test/test_model_services_service.py`

**Step 1: Write failing service tests**

Create `test/test_model_services_service.py` to verify:

- Creating a model service encrypts the key.
- Listing model services returns `has_api_key` and masked key only.
- Updating with missing `api_key` preserves the original key.
- Setting one service default clears default from others.

**Step 2: Run failing tests**

Run: `pytest "test/test_model_services_service.py" -q`

Expected: FAIL because schemas/services do not exist.

**Step 3: Implement schemas**

Create Pydantic models:

- `ModelServiceCreate`
- `ModelServiceUpdate`
- `ModelServiceResponse`
- `ModelServiceTestResponse`

Use `provider_type: Literal["openai_compatible"]` for first version.

Response must include:

```python
has_api_key: bool
api_key_masked: str | None
```

Response must not include `api_key_encrypted`.

**Step 4: Implement service functions**

Create functions:

- `list_model_services(db)`
- `create_model_service(db, data)`
- `update_model_service(db, service_id, data)`
- `delete_model_service(db, service_id)`
- `set_default_model_service(db, service_id)`
- `get_default_model_service(db)`

**Step 5: Verify**

Run: `pytest "test/test_model_services_service.py" -q`

Expected: PASS.

---

### Task 5: Add System API Endpoints For Model Services

**Files:**
- Modify: `backend/app/api/v1/system.py`
- Test: `test/test_model_services_api.py`

**Step 1: Write failing API tests**

Create `test/test_model_services_api.py` using an ASGI test client and admin dependency override. Cover:

- `GET /api/v1/system/model-services`
- `POST /api/v1/system/model-services`
- `PUT /api/v1/system/model-services/{id}`
- `POST /api/v1/system/model-services/{id}/set-default`
- `DELETE /api/v1/system/model-services/{id}`

Assert API key is never returned in plaintext.

**Step 2: Run failing tests**

Run: `pytest "test/test_model_services_api.py" -q`

Expected: FAIL because endpoints do not exist.

**Step 3: Implement routes**

Add routes to `backend/app/api/v1/system.py` under existing admin-only config section.

Use `get_admin_user` on every endpoint.

**Step 4: Verify**

Run: `pytest "test/test_model_services_api.py" -q`

Expected: PASS.

---

### Task 6: Add Model Service Test Connection

**Files:**
- Create: `backend/app/services/openai_compatible.py`
- Modify: `backend/app/services/model_services.py`
- Modify: `backend/app/api/v1/system.py`
- Test: `test/test_model_service_connection.py`

**Step 1: Write failing tests**

Use `httpx.MockTransport` or monkeypatch `httpx.AsyncClient.post` to verify:

- Test sends request to `{base_url}/chat/completions`.
- Authorization header uses decrypted key.
- Success updates `last_test_status = "success"`.
- Failure updates `last_test_status = "failure"`.

**Step 2: Run failing test**

Run: `pytest "test/test_model_service_connection.py" -q`

Expected: FAIL.

**Step 3: Implement OpenAI-compatible client**

Create helper:

```python
async def test_openai_compatible_service(service: ModelService) -> tuple[bool, str]:
    ...
```

Use a tiny request:

```json
{
  "model": "configured-model",
  "messages": [{"role": "user", "content": "ping"}],
  "max_tokens": 8,
  "temperature": 0
}
```

**Step 4: Verify**

Run: `pytest "test/test_model_service_connection.py" -q`

Expected: PASS.

---

### Task 7: Add LangGraph State And LLM Planner Adapter

**Files:**
- Create: `backend/app/agents/aidd/graph_state.py`
- Create: `backend/app/agents/aidd/llm_client.py`
- Create: `backend/app/agents/aidd/plan_schema.py`
- Test: `test/test_aidd_langgraph_planner_adapter.py`

**Step 1: Write failing tests**

Test that planner adapter:

- Builds a prompt containing user message, semantic inputs, and available capabilities.
- Parses valid JSON into a plan object.
- Rejects non-JSON output.
- Rejects tool slugs not present in `available_tools`.

**Step 2: Run failing test**

Run: `pytest "test/test_aidd_langgraph_planner_adapter.py" -q`

Expected: FAIL.

**Step 3: Implement state and schema**

Add:

- `AIDDGraphState`
- `AIDDGraphPlan`
- `AIDDGraphPlanStep`
- `parse_model_plan`
- `build_planning_prompt`

**Step 4: Verify**

Run: `pytest "test/test_aidd_langgraph_planner_adapter.py" -q`

Expected: PASS.

---

### Task 8: Build LangGraph Nodes

**Files:**
- Create: `backend/app/agents/aidd/graph_nodes.py`
- Test: `test/test_aidd_langgraph_nodes.py`

**Step 1: Write failing node tests**

Cover each node:

- `load_context` loads run/file metadata.
- `classify_input` produces semantic input.
- `discover_tools` filters unavailable tools.
- `validate_plan` rejects invalid tool/capability/input wiring.
- `replan_or_finish` returns `waiting_task`, `success`, or `failure`.

**Step 2: Run failing tests**

Run: `pytest "test/test_aidd_langgraph_nodes.py" -q`

Expected: FAIL.

**Step 3: Implement nodes**

Keep nodes thin and deterministic where possible. Only `plan_steps` calls the model service.

**Step 4: Verify**

Run: `pytest "test/test_aidd_langgraph_nodes.py" -q`

Expected: PASS.

---

### Task 9: Compile LangGraph And Integrate Agent Service

**Files:**
- Create: `backend/app/agents/aidd/graph.py`
- Modify: `backend/app/agents/aidd/service.py`
- Test: `test/test_aidd_langgraph_service.py`

**Step 1: Write failing service tests**

Cover:

- Creating a run without default model service fails with a clear message.
- Creating a run with a mocked planner creates `agent_run_steps`.
- Waiting task runs can be resumed by sync.
- Existing API response shape remains compatible with frontend.

**Step 2: Run failing tests**

Run: `pytest "test/test_aidd_langgraph_service.py" -q`

Expected: FAIL.

**Step 3: Implement graph compile function**

Create `build_aidd_graph()` using LangGraph `StateGraph`.

Route:

```text
load_context -> classify_input -> discover_tools -> plan_steps -> validate_plan -> execute_step -> observe_result -> replan_or_finish
```

Conditional edge after `replan_or_finish`:

- `execute_step`
- `success`
- `failure`
- `waiting_task`

**Step 4: Integrate service**

Replace direct `build_aidd_plan(...)` path in `create_agent_run` with graph invocation.

Keep `start_ready_steps`, `_schedule_step`, and reconciliation helpers where useful, but route new decisions through graph state.

**Step 5: Verify**

Run: `pytest "test/test_aidd_langgraph_service.py" -q`

Expected: PASS.

---

### Task 10: Add Frontend API Types For Model Services

**Files:**
- Modify: `frontend/src/types/models.d.ts`
- Modify: `frontend/src/api/system.ts`
- Test: `frontend/test/admin-model-services-surface.test.ts`

**Step 1: Write failing frontend surface test**

Create `frontend/test/admin-model-services-surface.test.ts`:

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('admin system page exposes model service management surface', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/views/admin/System.vue')), true)

  const systemApi = readSource('src/api/system.ts')
  const types = readSource('src/types/models.d.ts')
  const page = readSource('src/views/admin/System.vue')

  assert.equal(systemApi.includes('getModelServices'), true)
  assert.equal(systemApi.includes('createModelService'), true)
  assert.equal(systemApi.includes('testModelService'), true)
  assert.equal(types.includes('ModelService'), true)
  assert.equal(page.includes('model-services'), true)
  assert.equal(page.includes('api_key_encrypted'), false)
})
```

**Step 2: Run failing test**

Run: `node --test "test/admin-model-services-surface.test.ts"` from `frontend`.

Expected: FAIL.

**Step 3: Add API methods and types**

Add types:

- `ModelService`
- `ModelServiceCreateParams`
- `ModelServiceUpdateParams`
- `ModelServiceTestResult`

Add API methods:

- `getModelServices`
- `createModelService`
- `updateModelService`
- `deleteModelService`
- `testModelService`
- `setDefaultModelService`

**Step 4: Verify**

Run: `node --test "test/admin-model-services-surface.test.ts"`

Expected: PASS.

---

### Task 11: Add Admin Model Services UI

**Files:**
- Modify: `frontend/src/views/admin/System.vue`
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`
- Test: `frontend/test/admin-model-services-surface.test.ts`

**Step 1: Extend failing test**

Assert the page contains:

- `a-tabs`
- `modelServiceForm`
- `has_api_key`
- `testModelService`
- `setDefaultModelService`
- no plaintext key display bindings

**Step 2: Run failing test**

Run: `node --test "test/admin-model-services-surface.test.ts"` from `frontend`.

Expected: FAIL.

**Step 3: Implement UI**

Change `/admin/system` layout to tabs:

- overview
- model-services
- config

Model services tab:

- table
- create/edit drawer
- test connection button
- set default button
- delete confirmation

API Key behavior:

- display masked value only
- edit form key field placeholder says leaving blank keeps existing key

**Step 4: Verify**

Run: `node --test "test/admin-model-services-surface.test.ts"`

Expected: PASS.

---

### Task 12: Preserve Agent Frontend Simplicity

**Files:**
- Modify if needed: `frontend/src/components/workflow/AiddAgentPanel.vue`
- Test: `frontend/test/aidd-agent-surface.test.ts`

**Step 1: Strengthen existing surface test**

Assert Agent panel does not contain:

- `input_type`
- `a-radio-group`
- `generationCount`
- `LVPocket`
- `GCDM`

Assert it does contain:

- upload control
- research goal textarea
- capability strip
- runtime timeline

**Step 2: Run test**

Run: `node --test "test/aidd-agent-surface.test.ts"` from `frontend`.

Expected: PASS if no regression.

**Step 3: Fix if needed**

Only edit the Agent panel if the LangGraph integration changed frontend assumptions.

**Step 4: Verify**

Run: `node --test "test/aidd-agent-surface.test.ts"`

Expected: PASS.

---

### Task 13: Add End-To-End API Trial Script Or Test

**Files:**
- Create: `test/test_aidd_langgraph_api.py`

**Step 1: Write integration test**

Use ASGI test client with mocked model service and mocked task scheduling.

Assert:

- `POST /api/v1/agents/aidd/runs` accepts only `message` and `input_file_id`.
- Backend uses default model service.
- Response contains created steps.
- No frontend-controlled `input_type` is required.

**Step 2: Run failing test**

Run: `pytest "test/test_aidd_langgraph_api.py" -q`

Expected: FAIL until graph/service integration is complete.

**Step 3: Implement missing integration details**

Patch service and graph code until the test passes.

**Step 4: Verify**

Run: `pytest "test/test_aidd_langgraph_api.py" -q`

Expected: PASS.

---

### Task 14: Full Verification

**Files:**
- No source changes unless verification exposes failures.

**Step 1: Run backend focused tests**

Run:

```bash
pytest \
  "test/test_model_service_models.py" \
  "test/test_secret_crypto.py" \
  "test/test_model_services_service.py" \
  "test/test_model_services_api.py" \
  "test/test_model_service_connection.py" \
  "test/test_aidd_langgraph_planner_adapter.py" \
  "test/test_aidd_langgraph_nodes.py" \
  "test/test_aidd_langgraph_service.py" \
  "test/test_aidd_langgraph_api.py" \
  -q
```

Expected: PASS.

**Step 2: Run frontend focused tests**

Run from `frontend`:

```bash
node --test "test/admin-model-services-surface.test.ts"
node --test "test/aidd-agent-surface.test.ts"
```

Expected: PASS.

**Step 3: Run frontend build**

Run from `frontend`:

```bash
npm run build
```

Expected: PASS. Existing chunk-size or Vite externalization warnings may remain.

**Step 4: Run diff check**

Run from repo root:

```bash
git diff --check -- \
  "backend/app" \
  "backend/scripts" \
  "frontend/src" \
  "frontend/test" \
  "test"
```

Expected: PASS.

**Step 5: Manual API smoke test**

Start backend, create a model service as admin, test connection, then create an Agent run without `input_type`.

Expected:

- model service returns `has_api_key: true`
- API key never appears in response
- Agent run creates validated steps
- run can be resumed through sync

---

## Rollback Plan

If LangGraph integration causes runtime instability:

1. Keep `model_services` feature enabled.
2. Add temporary feature flag `AIDD_AGENT_ORCHESTRATOR=deterministic|langgraph`.
3. Route existing deterministic planner through the flag.
4. Keep API and frontend unchanged.

This preserves the user-facing Agent mode while isolating graph runtime issues.
