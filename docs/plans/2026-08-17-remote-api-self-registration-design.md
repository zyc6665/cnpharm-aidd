# Remote API Self Registration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace manual remote API tool registration with a platform-standard remote model service protocol that lets administrators register a tool from a service root URL, run an automatic smoke test, and publish only verified tools.

**Architecture:** The existing `remote_api` tool type becomes a standard `remote-tool.v1` executor path. Model services adapt to the platform contract through a fixed discovery manifest, asynchronous run polling, required logs/cancel endpoints, and standard `result.v2` outputs that flow into the existing ArtifactVersion persistence pipeline.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, Celery/direct task runner, existing Task state machine, existing standard Artifact registry, Vue 3, Pinia, Ant Design Vue, Vitest, pytest.

---

## Design Decisions

### Product Scope

- The old manual `remote_api` registration path is removed from the product surface.
- There are currently no registered legacy API tools, so no execution compatibility or migration is required for old `remote_api` configs.
- The first version supports one service root URL registering exactly one tool.
- The feature is an internal/controlled-environment model service standard, not a public third-party marketplace protocol.
- Remote services do not require authentication in v1 because they are expected to be deployed by the platform team in trusted infrastructure.
- URL SSRF restrictions are not added in v1; only administrator users may register remote services.

### Registration Input

Administrators provide the minimal platform-side fields:

```json
{
  "base_url": "https://model.example.com",
  "category_id": "tool-category-id",
  "run_smoke_test": true,
  "publish_on_success": false
}
```

The service root URL is the only remote technical entry point. The platform discovers the tool from fixed paths and manifest-declared same-service relative endpoints.

### Discovery Contract

The platform fetches the manifest from:

```text
GET /.well-known/sciminer-tool.json
```

The manifest may declare endpoint paths, but they must be relative paths under the same service root. The default required endpoints are:

```text
POST /invoke
GET  /runs/{remote_run_id}
GET  /runs/{remote_run_id}/logs
POST /runs/{remote_run_id}/cancel
GET  /runs/{remote_run_id}/artifacts
GET  /examples
GET  /health
```

### Manifest Format

The remote service returns a lightweight manifest that reuses the existing Tool Package v2 contract language instead of creating a second semantic system.

Minimum required manifest:

```json
{
  "api_version": "aidd.sciminer/remote-tool.v1",
  "kind": "RemoteTool",
  "metadata": {
    "slug": "lvpocket-api",
    "name": "LVpocket API",
    "version": "1.0.0",
    "description": "Pocket prediction service"
  },
  "artifacts": {
    "inputs": [
      {
        "name": "protein",
        "type": "protein_structure@1",
        "required": true
      }
    ],
    "outputs": [
      {
        "name": "pocket",
        "type": "binding_pocket@1",
        "cardinality": "one",
        "required": true
      }
    ]
  },
  "parameters_schema": {
    "type": "object",
    "properties": {},
    "additionalProperties": false
  },
  "endpoints": {
    "invoke": "/invoke",
    "status": "/runs/{remote_run_id}",
    "logs": "/runs/{remote_run_id}/logs",
    "cancel": "/runs/{remote_run_id}/cancel",
    "artifacts": "/runs/{remote_run_id}/artifacts",
    "examples": "/examples",
    "health": "/health"
  },
  "capabilities": {
    "async": true,
    "logs": true,
    "cancel": true,
    "progress": true
  }
}
```

Validation rules:

- `api_version` must be `aidd.sciminer/remote-tool.v1`.
- `kind` must be `RemoteTool`.
- `metadata.slug`, `metadata.name`, and `metadata.version` are required.
- `metadata.description` is required for platform display quality.
- `artifacts.inputs` and `artifacts.outputs` must each contain at least one entry.
- Artifact types must already exist in the platform-controlled standard Artifact registry.
- Unknown Artifact types reject registration, not just publishing.
- `parameters_schema` uses JSON Schema Draft-07, must have top-level `type: "object"`, and must not contain file inputs.
- `endpoints.invoke`, `status`, `logs`, `cancel`, and `artifacts` are required.
- `capabilities.async`, `logs`, and `cancel` must be `true` in v1.

### Metadata Ownership

The remote manifest owns technical contract fields:

- `slug`
- `name`
- `version`
- `description`
- `parameters_schema`
- `artifacts`
- `endpoints`
- `capabilities`

The platform registration request owns or may override operational display fields:

- `category_id`
- `tags`
- `icon`
- `icon_url`
- `is_public`
- `timeout_sec`

`gpu_required` defaults to `false` for remote API tools because GPU allocation is managed by the remote model service.

### Versioning

The platform manages versions by `slug + metadata.version`:

- Missing `slug`: create `Tool` and `ToolVersion`.
- Existing `slug`, new `version`: create a new `ToolVersion`.
- Existing `slug`, same unpublished version: update the draft version.
- Existing `slug`, same published version: reject silent overwrite and require a new semantic version.
- Historical versions remain available for reproducibility.

### Registration Diagnostics

The registration endpoint returns stage-level diagnostics, not one opaque error string.

Expected stage names:

- `fetch_manifest`
- `validate_manifest`
- `health_check`
- `fetch_examples`
- `persist_draft`
- `create_smoke_test`
- `publish_on_success`

Example response shape:

```json
{
  "tool_id": "tool-id-or-null",
  "tool_version_id": "version-id-or-null",
  "stages": [
    {
      "name": "fetch_manifest",
      "status": "success",
      "message": "Manifest loaded"
    },
    {
      "name": "validate_manifest",
      "status": "failure",
      "message": "artifacts.outputs[0].type unknown: foo@1",
      "detail": {}
    }
  ],
  "smoke_test_task_id": null
}
```

Behavior by stage:

- Manifest fetch failure: do not persist a tool.
- Manifest schema failure: do not persist a tool.
- Health failure: persist draft with warning diagnostics.
- Missing examples: persist draft, but publishing is blocked.
- Smoke test creation failure: persist draft.
- Smoke test execution failure: keep draft and block publishing.
- Publish failure: keep draft and expose the publish-stage diagnostic.

### Examples And Smoke Tests

Remote services should expose examples through the manifest or `GET /examples`.

Example shape:

```json
{
  "examples": [
    {
      "name": "default",
      "description": "Smoke test sample",
      "smoke": true,
      "parameters": {
        "threshold": 0.5
      },
      "input_artifacts": {
        "protein": {
          "type": "protein_structure@1",
          "files": {
            "pdb": {
              "filename": "protein.pdb",
              "content_type": "chemical/x-pdb",
              "url": "/examples/default/protein.pdb",
              "sha256": "64-hex-sha256"
            }
          }
        }
      }
    }
  ]
}
```

Rules:

- Draft registration may succeed without a smoke example.
- Publishing requires a valid smoke example.
- If no example has `smoke: true`, the first example is the smoke example.
- Examples must cover all required Artifact inputs.
- Example parameters must validate against `parameters_schema`.
- File examples may be returned as relative URLs or small inline content.
- URL files are preferred.
- Inline file content is allowed for files up to 1 MB.
- Downloaded example files must match declared `sha256`.

Smoke test execution uses the normal platform Task system:

- Lightweight manifest, schema, health, and example checks happen synchronously in the registration request.
- The real smoke test creates a platform `Task` with `extra_data.smoke_test = true`.
- The Task uses the same remote API executor that real user runs will use.
- On success, the platform writes a validation summary to `ToolVersion.config.last_smoke_test` and keeps the full Task history.
- Publishing requires `last_smoke_test.status == "success"` and `last_smoke_test.manifest_sha256` matching the current manifest hash.

Suggested config summary:

```json
{
  "last_smoke_test": {
    "status": "success",
    "task_id": "platform-task-id",
    "remote_run_id": "run_123",
    "tested_at": "2026-08-17T10:00:00Z",
    "example_name": "default",
    "manifest_sha256": "64-hex-sha256",
    "result_summary": {
      "artifact_refs": ["pocket"]
    }
  }
}
```

If `publish_on_success` is requested, the backend performs the publish after the smoke test succeeds. The frontend does not own this state transition.

### Invoke Request

Remote execution always uses a fixed JSON envelope. v1 does not support arbitrary request mapping.

```json
{
  "request_id": "uuid",
  "task": {
    "id": "platform-task-id",
    "tool_slug": "lvpocket-api",
    "tool_version": "1.0.0"
  },
  "inputs": {
    "protein": {
      "artifact_version_id": "artifact-version-id",
      "type": "protein_structure@1",
      "files": {
        "pdb": {
          "url": "https://platform.example.com/api/v1/files/file-id/download?token=short-lived-token",
          "filename": "protein.pdb",
          "sha256": "64-hex-sha256",
          "content_type": "chemical/x-pdb"
        }
      },
      "metadata": {}
    }
  },
  "parameters": {
    "threshold": 0.5
  },
  "context": {
    "project_id": "project-id",
    "user_id": "user-id"
  }
}
```

Input files are passed as short-lived platform download URLs. The remote service downloads them and may verify `sha256`. The platform should generate per-file, per-task signed URLs rather than exposing normal authenticated user download URLs.

### Asynchronous Run Protocol

`POST /invoke` returns a remote run handle, not final results:

```json
{
  "remote_run_id": "run_abc123",
  "status": "queued",
  "status_url": "/runs/run_abc123",
  "logs_url": "/runs/run_abc123/logs",
  "artifacts_url": "/runs/run_abc123/artifacts",
  "cancel_url": "/runs/run_abc123/cancel"
}
```

The platform polls `GET /runs/{remote_run_id}`. Main statuses are fixed:

```text
queued
running
success
failure
canceled
```

Detailed state is carried through optional fields:

```json
{
  "remote_run_id": "run_123",
  "status": "running",
  "phase": "model_inference",
  "progress": 42.5,
  "message": "Running pocket prediction",
  "started_at": "2026-08-17T10:00:00Z",
  "updated_at": "2026-08-17T10:01:30Z",
  "finished_at": null,
  "error": null
}
```

Status mapping:

- `queued` maps to platform pending/running wait state.
- `running` maps to platform running.
- `success` maps to platform success after artifact collection succeeds.
- `failure` maps to platform failure.
- `canceled` maps to platform canceled.

### Logs

Logs are required in v1.

```text
GET /runs/{remote_run_id}/logs?cursor=...
```

Response:

```json
{
  "items": [
    {
      "timestamp": "2026-08-17T10:01:30Z",
      "level": "INFO",
      "message": "Loading model weights"
    }
  ],
  "next_cursor": "abc",
  "has_more": true
}
```

### Cancellation

Cancellation is required in v1.

```text
POST /runs/{remote_run_id}/cancel
```

Rules:

- The endpoint must be idempotent.
- If the remote run is queued or running, the remote service must attempt to terminate it.
- If the run is already terminal, the endpoint returns the current terminal state.
- The remote service must eventually report `status: "canceled"` for successfully canceled runs.
- If physical termination takes time, the service may keep `status: "running"` with `phase: "canceling"` until the terminal canceled state.
- After a platform task is canceled locally, a later remote success must not overwrite the platform task back to success.

### Result Artifacts

Remote services must return the existing standard result format:

```text
GET /runs/{remote_run_id}/artifacts
```

Response:

```json
{
  "result_version": "aidd.sciminer/result.v2",
  "artifacts": [
    {
      "ref": "pocket",
      "type": "binding_pocket@1",
      "files": {
        "pdb": {
          "path": "output/pocket.pdb",
          "sha256": "64-hex-sha256",
          "content_type": "chemical/x-pdb",
          "url": "/runs/run_123/files/output/pocket.pdb"
        }
      },
      "metadata": {}
    }
  ],
  "relations": []
}
```

The platform downloads every output file into its own storage backend, validates `sha256`, creates platform `File` rows, then persists `ArtifactVersion` and lineage through the existing standard Artifact service. The platform must not keep only remote URLs for reproducible outputs.

## Implementation Plan

### Task 1: Remote Tool Manifest Schema

**Files:**

- Create: `backend/app/remote_tools/__init__.py`
- Create: `backend/app/remote_tools/schemas.py`
- Create: `test/test_remote_tool_manifest.py`

**Steps:**

1. Add Pydantic models for `RemoteToolManifest`, metadata, Artifact input/output declarations, endpoint declarations, capabilities, and example declarations.
2. Validate `api_version`, `kind`, required endpoints, required capabilities, and JSON Schema Draft-07 object parameters.
3. Reuse `app.artifact_standards.registry.is_standard_artifact_ref` to reject unknown Artifact types.
4. Add tests for valid manifest, missing required endpoints, unknown Artifact refs, invalid parameter schema, and absolute endpoint paths.
5. Run `pytest test/test_remote_tool_manifest.py -v`.

### Task 2: Remote Tool Client And Diagnostics

**Files:**

- Create: `backend/app/remote_tools/client.py`
- Create: `backend/app/remote_tools/diagnostics.py`
- Test: `test/test_remote_tool_registration.py`

**Steps:**

1. Add a client that normalizes `base_url`, fetches the discovery manifest, health, and examples.
2. Add stage diagnostic data structures with `name`, `status`, `message`, and `detail`.
3. Include request timeout handling and fixed request headers such as `X-Sciminer-Request-Id`.
4. Keep URL validation intentionally minimal for v1 because administrator-only trusted services are in scope.
5. Add tests for successful staged diagnostics and each failure stage.
6. Run `pytest test/test_remote_tool_registration.py -v`.

### Task 3: Register Remote API Route

**Files:**

- Modify: `backend/app/schemas/tools.py`
- Modify: `backend/app/api/v1/tools_admin.py`
- Modify: `backend/app/api/v1/tool_route_utils.py`
- Test: `test/test_tool_import_api.py`
- Test: `test/test_remote_tool_registration.py`

**Steps:**

1. Add `RemoteToolRegisterRequest` and response schema helpers.
2. Add `POST /api/v1/tools/register-remote` for admin users.
3. Fetch and validate manifest synchronously.
4. Require `category_id` through existing active category validation.
5. Create/update `Tool` and `ToolVersion` using `type: "remote_api"` and `mode: "remote_tool_v1"`.
6. Store `base_url`, manifest, manifest hash, endpoint map, parameters schema, Artifact contract, diagnostics, and publish-on-success intent in `ToolVersion.config`.
7. Reject overwrite of a published `slug + version`.
8. Preserve the existing `success_response` style.
9. Run `pytest test/test_remote_tool_registration.py test/test_tool_import_api.py -v`.

### Task 4: Signed File URLs For Remote Inputs

**Files:**

- Create or modify: `backend/app/files/remote_access_tokens.py`
- Modify: `backend/app/api/v1/files.py`
- Modify: `backend/app/tasks/executors/remote_api.py`
- Test: `test/test_remote_tool_signed_file_urls.py`

**Steps:**

1. Add short-lived file download token creation and validation for a specific file and task.
2. Extend the download endpoint to accept the token without requiring user bearer authentication.
3. Ensure tokens expire and cannot access other file IDs.
4. Build remote input file URLs from ArtifactVersion file bindings and standard input declarations.
5. Add tests for valid token access, expired token rejection, file mismatch rejection, and remote invoke payload construction.
6. Run `pytest test/test_remote_tool_signed_file_urls.py -v`.

### Task 5: Standard Async Remote API Executor

**Files:**

- Modify: `backend/app/tasks/executors/remote_api.py`
- Modify: `backend/app/tasks/executors/factory.py` if needed
- Test: `test/test_remote_api_executor.py`
- Test: `test/test_worker_notifications.py`

**Steps:**

1. Replace old arbitrary endpoint execution with `remote_tool_v1` invoke and polling behavior.
2. Send the fixed invoke envelope with `request_id`, task context, Artifact inputs, parameters, and signed input URLs.
3. Persist `remote_run_id` in task `extra_data` or execution metadata.
4. Poll status until `success`, `failure`, or `canceled`, updating platform progress and messages.
5. Poll logs with cursor and append new remote logs to platform task logs.
6. On cancel requests, call the required remote cancel endpoint and keep platform cancellation authoritative.
7. On success, collect remote `result.v2` and download every output file into platform storage before standard Artifact persistence.
8. Add tests for queued/running/success flow, failure flow, log cursor flow, cancellation flow, and output file checksum mismatch.
9. Run `pytest test/test_remote_api_executor.py test/test_worker_notifications.py -v`.

### Task 6: Smoke Test Task And Publish Gate

**Files:**

- Modify: `backend/app/tasks/service.py`
- Modify: `backend/app/worker/tasks.py`
- Modify: `backend/app/api/v1/tools_admin.py`
- Modify: `backend/app/api/v1/tool_route_utils.py`
- Test: `test/test_remote_tool_smoke_test.py`

**Steps:**

1. Add a helper to schedule smoke test tasks from remote examples.
2. Mark smoke test tasks with `extra_data.smoke_test = true`, `tool_version_id`, `manifest_sha256`, and `publish_on_success` intent.
3. Convert remote example input artifacts into platform files and ArtifactVersion bindings for the smoke test.
4. After a smoke test succeeds, write `ToolVersion.config.last_smoke_test` with task ID, remote run ID, tested time, example name, manifest hash, and output summary.
5. If publish-on-success is pending, call the same validation logic used by manual publish.
6. Change manual publish validation to require matching successful smoke test for `mode: "remote_tool_v1"`.
7. Add tests for missing smoke example blocking publish, failed smoke test blocking publish, manifest hash mismatch blocking publish, and backend auto-publish after smoke success.
8. Run `pytest test/test_remote_tool_smoke_test.py -v`.

### Task 7: Frontend Registration Flow

**Files:**

- Modify: `frontend/src/api/tools.ts`
- Modify: `frontend/src/views/tools/Create.vue`
- Modify: `frontend/src/domain/tools/tool-config.ts`
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`
- Test: `frontend/src/domain/tools/tool-config.spec.ts`

**Steps:**

1. Remove the manual remote API endpoint/schema form from the creation surface.
2. Add a remote model service registration mode with fields for `base_url`, `category_id`, `run_smoke_test`, and `publish_on_success`.
3. Call `POST /api/v1/tools/register-remote`.
4. Render stage diagnostics in a compact result panel.
5. Show smoke test task link when returned.
6. Keep Docker, Python, and SSH registration paths unchanged unless tests show direct coupling.
7. Run `cd frontend && npm run test -- tool-config.spec.ts`.

### Task 8: Contract And Regression Tests

**Files:**

- Create: `test/test_remote_tool_contract.py`
- Modify: `test/test_backend_architecture_boundaries.py`
- Modify: `test/test_executor_module_layout.py`

**Steps:**

1. Add end-to-end-style tests with a fake remote model service transport.
2. Cover registration, draft persistence, smoke task creation, async execution, logs, cancel, result.v2 artifact persistence, and publish gate.
3. Update architecture tests to allow the new `remote_tools` module and ensure route code does not contain executor logic.
4. Run focused tests:

```bash
pytest test/test_remote_tool_manifest.py test/test_remote_tool_registration.py test/test_remote_tool_contract.py test/test_remote_tool_smoke_test.py -v
```

5. Run full backend tests:

```bash
pytest test
```

6. Run frontend checks:

```bash
cd frontend && npm run test && npm run build
```

### Task 9: Documentation And Operator Notes

**Files:**

- Create: `docs/guides/remote-tool-v1-authoring.md`
- Modify: `README.md`
- Modify: `docs/guides/tool-package-authoring.md` if cross-reference is useful

**Steps:**

1. Document the manifest contract, endpoints, invoke envelope, status schema, logs schema, cancel semantics, examples, and result.v2 requirements.
2. Add a minimal remote service implementation checklist.
3. Add a note that remote services are trusted internal services in v1 and do not use remote API authentication.
4. Document that output files are copied into platform storage and input files are passed by short-lived signed URLs.
5. Run docs-related consistency tests if present:

```bash
pytest test/test_readme_consistency.py -v
```

## Atomic Commit Plan

The implementation should be committed as one atomic feature commit after all code, docs, and tests are complete. Do not include unrelated existing workspace changes.

Suggested final commands:

```bash
git status --short
git add \
  backend/app/remote_tools \
  backend/app/api/v1/tools_admin.py \
  backend/app/api/v1/tool_route_utils.py \
  backend/app/schemas/tools.py \
  backend/app/tasks/executors/remote_api.py \
  backend/app/tasks/service.py \
  backend/app/worker/tasks.py \
  backend/app/files/remote_access_tokens.py \
  frontend/src/api/tools.ts \
  frontend/src/views/tools/Create.vue \
  frontend/src/domain/tools/tool-config.ts \
  frontend/src/locales/zh-CN/index.ts \
  frontend/src/locales/en-US/index.ts \
  test/test_remote_tool_manifest.py \
  test/test_remote_tool_registration.py \
  test/test_remote_tool_signed_file_urls.py \
  test/test_remote_api_executor.py \
  test/test_remote_tool_smoke_test.py \
  test/test_remote_tool_contract.py \
  docs/guides/remote-tool-v1-authoring.md \
  docs/plans/2026-08-17-remote-api-self-registration-design.md
git commit -m "feat: add remote API self registration"
```

Before committing in this workspace, inspect `git status --short` and avoid staging unrelated deleted docs, `func_detail/`, `model/`, or other pre-existing changes.

