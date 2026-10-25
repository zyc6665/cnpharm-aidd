# Standard Artifact Run Context Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let tools run independently or inside a project while keeping Standard Artifact inputs deterministic and workflow bindings automatic.

**Architecture:** Separate tool contracts from invocation scope by introducing a Run Context and shared Artifact Binding Resolver model. Existing ArtifactVersion bindings remain project-scoped; direct uploads can satisfy Standard Artifact input slots as staged task inputs; Standard Artifact outputs resolve to the explicit project or the user's default workspace project.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic, pytest, Vue 3, TypeScript, Vitest, existing task scheduler, Tool Package v2 request/result contracts, existing workflow canvas modules.

---

### Task 1: Add Frontend Run Context Policy Module

**Files:**
- Create: `frontend/src/domain/tools/standard-artifact-run-context.ts`
- Create: `frontend/src/domain/tools/standard-artifact-run-context.spec.ts`
- Modify: `frontend/src/domain/tools/index.ts`

**Step 1: Write failing tests**

Add tests for the policy behavior:

```ts
import { describe, expect, it } from 'vitest'
import {
  buildStandardRunTaskExtras,
  hasProjectScopedArtifactBindings,
  resolveStandardRunContext,
} from './standard-artifact-run-context'

describe('standard artifact run context', () => {
  it('allows standard-output tools to run without explicit project', () => {
    expect(resolveStandardRunContext({ projectId: undefined, emitsStandardArtifacts: true })).toEqual({
      projectId: undefined,
      outputScope: 'default_workspace',
    })
  })

  it('requires project only when binding existing ArtifactVersions', () => {
    expect(hasProjectScopedArtifactBindings({ protein: 'version-1' })).toBe(true)
    expect(hasProjectScopedArtifactBindings({})).toBe(false)
  })

  it('serializes project bindings and staged uploads separately', () => {
    expect(buildStandardRunTaskExtras({
      projectId: 'project-1',
      inputBindings: { protein: 'version-1' },
      standardInputUploads: { ligand: 'file-1' },
    })).toEqual({
      project_id: 'project-1',
      input_bindings: { protein: 'version-1' },
      standard_input_uploads: { ligand: 'file-1' },
    })
  })
})
```

Run:

```bash
cd frontend && npm test -- standard-artifact-run-context.spec.ts
```

Expected: fail because the module does not exist.

**Step 2: Implement minimal policy module**

Create `frontend/src/domain/tools/standard-artifact-run-context.ts`:

```ts
import type { TaskCreateParams } from '@/types/models'

export type StandardRunOutputScope = 'project' | 'default_workspace' | 'file_only'

export interface StandardRunContextInput {
  projectId?: string | null
  emitsStandardArtifacts?: boolean
}

export interface StandardRunTaskExtrasInput {
  projectId?: string | null
  inputBindings: Record<string, string>
  standardInputUploads: Record<string, string>
}

function compactRecord(value: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(value).filter(([, item]) => typeof item === 'string' && item.trim())
  )
}

export function resolveStandardRunContext(input: StandardRunContextInput) {
  const projectId = input.projectId?.trim() || undefined
  return {
    projectId,
    outputScope: projectId
      ? 'project'
      : input.emitsStandardArtifacts
        ? 'default_workspace'
        : 'file_only' as StandardRunOutputScope,
  }
}

export function hasProjectScopedArtifactBindings(inputBindings: Record<string, string>) {
  return Object.keys(compactRecord(inputBindings)).length > 0
}

export function buildStandardRunTaskExtras(
  input: StandardRunTaskExtrasInput,
): Pick<TaskCreateParams, 'project_id' | 'input_bindings' | 'standard_input_uploads'> {
  const projectId = input.projectId?.trim()
  const inputBindings = compactRecord(input.inputBindings)
  const standardInputUploads = compactRecord(input.standardInputUploads)
  return {
    ...(projectId ? { project_id: projectId } : {}),
    ...(Object.keys(inputBindings).length ? { input_bindings: inputBindings } : {}),
    ...(Object.keys(standardInputUploads).length ? { standard_input_uploads: standardInputUploads } : {}),
  }
}
```

Export it from `frontend/src/domain/tools/index.ts`.

**Step 3: Run tests**

```bash
cd frontend && npm test -- standard-artifact-run-context.spec.ts
```

Expected: pass.

**Step 4: Commit**

```bash
git add frontend/src/domain/tools/standard-artifact-run-context.ts \
  frontend/src/domain/tools/standard-artifact-run-context.spec.ts \
  frontend/src/domain/tools/index.ts
git commit -m "feat: add standard artifact run context policy"
```

### Task 2: Extend Task Create Contract for Staged Standard Inputs

**Files:**
- Modify: `backend/app/schemas/tasks.py`
- Modify: `frontend/src/types/models.d.ts`
- Test: `test/test_tasks_service_standard_inputs.py`

**Step 1: Write failing backend schema/service test**

Add a focused test that creates `TaskCreate(standard_input_uploads={...})` and expects the value to be accepted by the schema.

```py
from app.schemas.tasks import TaskCreate

def test_task_create_accepts_standard_input_uploads():
    payload = TaskCreate(
        tool_id='tool-1',
        standard_input_uploads={'protein': 'file-1'},
    )
    assert payload.standard_input_uploads == {'protein': 'file-1'}
```

Run:

```bash
pytest test/test_tasks_service_standard_inputs.py::test_task_create_accepts_standard_input_uploads -q
```

Expected: fail because `standard_input_uploads` is not defined.

**Step 2: Add backend field**

In `backend/app/schemas/tasks.py`, add to `TaskCreate` and `TaskInputSchema`:

```py
standard_input_uploads: Dict[str, str] = Field(
    default_factory=dict,
    description='标准 Artifact 输入槽的直接上传文件绑定，按 input name 索引',
)
```

**Step 3: Add frontend type field**

In `frontend/src/types/models.d.ts`, add to `TaskCreateParams`:

```ts
standard_input_uploads?: Record<string, string>
```

**Step 4: Run schema tests**

```bash
pytest test/test_tasks_service_standard_inputs.py::test_task_create_accepts_standard_input_uploads -q
cd frontend && npm run build
```

Expected: pass.

**Step 5: Commit**

```bash
git add backend/app/schemas/tasks.py frontend/src/types/models.d.ts test/test_tasks_service_standard_inputs.py
git commit -m "feat: accept staged standard input uploads"
```

### Task 3: Extract Backend Standard Task Input Preparation Module

**Files:**
- Create: `backend/app/tasks/standard_inputs.py`
- Modify: `backend/app/tasks/service.py`
- Test: `test/test_tasks_service_standard_inputs.py`

**Step 1: Write failing tests for backend authority behavior**

Cover these cases:

```py
async def test_existing_artifact_binding_without_project_is_rejected(db_session):
    # Build a TaskCreate with input_bindings and no project_id.
    # Expected: ValidationException('标准 ArtifactVersion 输入绑定必须提供 project_id')

async def test_standard_output_without_project_resolves_default_project(db_session, user, standard_output_tool):
    # Create a standard-output tool and TaskCreate(project_id=None).
    # Expected: task.extra_data['project_id'] is populated.

async def test_staged_standard_uploads_are_recorded_in_extra_data(db_session, user, standard_input_tool, uploaded_file):
    # Create task with standard_input_uploads={'protein': uploaded_file.id}.
    # Expected: task.extra_data['standard_input_uploads'] contains the slot mapping.
```

Run:

```bash
pytest test/test_tasks_service_standard_inputs.py -q
```

Expected: fail because staged upload preparation is not implemented.

**Step 2: Move existing private helpers into a module**

Create `backend/app/tasks/standard_inputs.py` with:

```py
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class StandardTaskInputProjection:
    project_id: str | None
    input_bindings: dict[str, str] = field(default_factory=dict)
    standard_input_uploads: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    file_ids: list[str] = field(default_factory=list)
    binding_decisions: dict[str, dict[str, Any]] = field(default_factory=dict)
```

Move or wrap these behaviors from `backend/app/tasks/service.py`:

- `_validate_standard_input_bindings`
- `_project_standard_input_bindings`
- `_project_selected_file_to_legacy_params`
- `_tool_config_emits_standard_artifacts`

Expose one function:

```py
async def prepare_standard_task_inputs(
    db,
    *,
    current_user,
    tool,
    tool_version,
    project_id,
    input_bindings,
    standard_input_uploads,
    params,
    file_ids,
) -> StandardTaskInputProjection:
    ...
```

Rules:

- If `input_bindings` is non-empty, require explicit `project_id` and validate all versions belong to that project.
- If `standard_input_uploads` is non-empty and `project_id` is absent, use `ensure_migration_project_for_owner` to get a default workspace project.
- If the tool emits Standard Artifact outputs and `project_id` is absent, use `ensure_migration_project_for_owner`.
- Add staged upload file ids to `file_ids` so normal task storage can access them.
- Preserve role/readiness binding decisions for existing ArtifactVersion bindings.

**Step 3: Wire task service through the new module**

In `backend/app/tasks/service.py`, replace the inline project/input block with:

```py
projection = await prepare_standard_task_inputs(
    db,
    current_user=current_user,
    tool=tool,
    tool_version=tool_version,
    project_id=task_data.project_id,
    input_bindings=task_data.input_bindings,
    standard_input_uploads=task_data.standard_input_uploads,
    params=dict(task_data.params or {}),
    file_ids=list(task_data.file_ids or []),
)
project_id = projection.project_id
params = projection.params
file_ids = projection.file_ids
if projection.input_bindings:
    extra_data['input_bindings'] = projection.input_bindings
if projection.standard_input_uploads:
    extra_data['standard_input_uploads'] = projection.standard_input_uploads
if projection.binding_decisions:
    extra_data['binding_decisions'] = projection.binding_decisions
if project_id:
    extra_data['project_id'] = project_id
```

**Step 4: Run backend tests**

```bash
pytest test/test_tasks_service_standard_inputs.py test/test_tool_contracts.py -q
```

Expected: pass.

**Step 5: Commit**

```bash
git add backend/app/tasks/standard_inputs.py backend/app/tasks/service.py \
  backend/app/schemas/tasks.py test/test_tasks_service_standard_inputs.py
git commit -m "feat: centralize standard task input preparation"
```

### Task 4: Support Staged Standard Inputs in Request Builders

**Files:**
- Modify: `backend/app/execution/standard_contracts.py`
- Modify: `backend/app/execution/request_builder.py`
- Modify: `backend/app/tasks/executors/ssh_job.py`
- Modify: `backend/app/tasks/executors/remote_api.py`
- Test: `test/test_standard_execution_request_builder.py`

**Step 1: Write failing request-builder tests**

Add tests for staged uploads:

```py
async def test_build_request_accepts_staged_standard_input_file(db_session, task, protein_manifest, uploaded_pdb):
    request = await build_standard_execution_request(
        db_session,
        task=task,
        tool_package_manifest=protein_manifest,
        input_bindings={},
        standard_input_uploads={'protein': uploaded_pdb.id},
        parameters={},
        work_dir=tmp_path,
        execution_context=context,
    )
    assert request.inputs['protein'].source == 'staged_file'
    assert 'structure_file' in request.inputs['protein'].files
```

Run:

```bash
pytest test/test_standard_execution_request_builder.py -q
```

Expected: fail because `standard_input_uploads` and staged-file source are unsupported.

**Step 2: Extend request contract without breaking ArtifactVersion inputs**

In `StandardInputArtifact`, add:

```py
source: Literal['artifact_version', 'staged_file'] = 'artifact_version'
artifact_version_id: str | None = None
```

Keep existing ArtifactVersion request shape compatible by defaulting `source` and still populating `artifact_version_id` for persisted bindings.

**Step 3: Add request builder branch**

Update `build_standard_execution_request(...)` signature:

```py
standard_input_uploads: dict[str, str] | None = None
```

For each declaration:

1. Prefer `input_bindings[declaration.name]` when present.
2. Else use `standard_input_uploads[declaration.name]`.
3. If neither exists and required, raise missing input.

For staged files, load `FileModel`, choose the primary Standard Artifact role, stage the file under `input/<slot>/<role>/<filename>`, and return:

```py
StandardInputArtifact(
    source='staged_file',
    artifact_version_id=None,
    type=declaration.type,
    files={primary_role: file_ref},
    metadata={'source': 'direct_upload', 'filename': file_record.filename},
)
```

Do not claim staged uploads are persisted Standard Artifacts. They are deterministic task inputs for standalone execution.

**Step 4: Wire executors**

In SSH and remote API executors, read:

```py
standard_input_uploads = (self.task.extra_data or {}).get('standard_input_uploads') or {}
```

Pass it to `build_standard_execution_request(...)`.

**Step 5: Run backend tests**

```bash
pytest test/test_standard_execution_request_builder.py test/test_tool_contracts.py -q
```

Expected: pass.

**Step 6: Commit**

```bash
git add backend/app/execution/standard_contracts.py backend/app/execution/request_builder.py \
  backend/app/tasks/executors/ssh_job.py backend/app/tasks/executors/remote_api.py \
  test/test_standard_execution_request_builder.py
git commit -m "feat: stage uploaded standard inputs for tool runs"
```

### Task 5: Update Tool Detail Page Standard Input UX

**Files:**
- Modify: `frontend/src/views/tools/Detail.vue`
- Modify: `frontend/src/domain/tools/standard-artifact-inputs.ts`
- Modify: `frontend/src/domain/tools/standard-artifact-inputs.spec.ts`
- Test: `frontend/src/views/tools/Detail.spec.ts` or existing closest tool detail test

**Step 1: Write failing frontend tests**

Cover:

- No `project_id` no longer disables submit solely because Standard Artifact slots exist.
- Existing Artifact selector is disabled without project, but upload is available.
- Submit with uploaded Standard input sends `standard_input_uploads` and no `project_id`.
- Submit with selected project Artifact sends `input_bindings` and `project_id`.

Run:

```bash
cd frontend && npm test -- standard-artifact-inputs.spec.ts Detail.spec.ts
```

Expected: fail because UI still hard-blocks missing project and has no staged upload map.

**Step 2: Extend standard input helper**

Add:

```ts
export function buildStandardInputUploadBindings(
  selectedUploads: Record<string, { id?: string | number } | undefined>,
): Record<string, string> {
  return Object.fromEntries(
    Object.entries(selectedUploads)
      .map(([slotName, file]) => [slotName, file?.id ? String(file.id) : ''])
      .filter(([, fileId]) => fileId)
  )
}
```

Deprecate `buildStandardTaskRequestExtras` by delegating to `buildStandardRunTaskExtras` from Task 1.

**Step 3: Update UI controls**

For each Standard Artifact slot:

- Render project Artifact select when `currentProjectId` exists.
- Render upload control always.
- If no project, replace warning with: “未进入项目时可直接上传文件运行；进入项目后可复用已有 Artifact。”

Remove:

```ts
if (standardInputSlots.value.length && !currentProjectId.value) return false
```

Replace required-slot check with “selected ArtifactVersion or staged upload exists”.

**Step 4: Update submit payload**

Build:

```ts
const standardInputUploads = buildStandardInputUploadBindings(selectedStandardInputUploads)
const task = await tasksStore.createTask({
  ...,
  ...buildStandardRunTaskExtras({
    projectId: currentProjectId.value,
    inputBindings: standardInputBindings.value,
    standardInputUploads,
  }),
})
```

**Step 5: Run frontend tests and build**

```bash
cd frontend && npm test -- standard-artifact-run-context.spec.ts standard-artifact-inputs.spec.ts Detail.spec.ts
cd frontend && npm run build
```

Expected: pass.

**Step 6: Commit**

```bash
git add frontend/src/views/tools/Detail.vue frontend/src/domain/tools/standard-artifact-inputs.ts \
  frontend/src/domain/tools/standard-artifact-inputs.spec.ts frontend/src/views/tools/Detail.spec.ts
git commit -m "feat: allow standalone standard artifact inputs"
```

### Task 6: Align Standalone Canvas Node Runs

**Files:**
- Modify: `frontend/src/composables/useStandaloneNodeRun.ts`
- Modify: `frontend/src/composables/useStandaloneNodeRun.spec.ts`
- Modify: `frontend/src/components/workflow/WorkflowNodeRunPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowNodeRunPanel.spec.ts`

**Step 1: Write failing tests**

Cover:

- Node standalone run with project Artifact sends `input_bindings` and `project_id`.
- Node standalone run with uploaded Standard input sends `standard_input_uploads`.
- Missing project does not trigger the old `Task extra_data.project_id` failure path.

Run:

```bash
cd frontend && npm test -- useStandaloneNodeRun.spec.ts WorkflowNodeRunPanel.spec.ts
```

Expected: fail because node standalone logic only knows selected artifacts and generic uploaded files.

**Step 2: Reuse frontend run context helpers**

Update `useStandaloneNodeRun.ts` to accept `standardInputUploads` in `StandaloneNodeRunOptions` and send them via `buildStandardRunTaskExtras`.

**Step 3: Update node panel UI**

Mirror the tool detail behavior:

- Project Artifact select when project exists.
- Upload fallback for every required Standard Artifact slot.
- Required state is satisfied by either a compatible ArtifactVersion or an upload.

**Step 4: Run tests**

```bash
cd frontend && npm test -- useStandaloneNodeRun.spec.ts WorkflowNodeRunPanel.spec.ts
```

Expected: pass.

**Step 5: Commit**

```bash
git add frontend/src/composables/useStandaloneNodeRun.ts frontend/src/composables/useStandaloneNodeRun.spec.ts \
  frontend/src/components/workflow/WorkflowNodeRunPanel.vue \
  frontend/src/components/workflow/WorkflowNodeRunPanel.spec.ts
git commit -m "feat: support standalone canvas standard inputs"
```

### Task 7: Preserve Workflow Auto-Binding Semantics

**Files:**
- Modify: `backend/app/services/workflow_scheduler.py`
- Modify: `backend/app/services/workflow_runs.py`
- Modify: `frontend/src/workflow/preflight.ts`
- Test: `test/test_workflow_standard_artifact_bindings.py`
- Test: `frontend/src/workflow/preflight.spec.ts`

**Step 1: Write failing workflow regression tests**

Cover Fetch PDB -> LVpocket:

```py
async def test_workflow_uses_upstream_standard_artifact_version_for_downstream_slot(...):
    # Source node produces standard_artifacts.protein with artifact_version_id.
    # Downstream lvpocket slot protein receives input_bindings['protein'].
```

Cover projectless standard-output workflow:

```py
async def test_projectless_standard_output_workflow_resolves_default_project(...):
    # Workflow definition has project_id None but node emits Standard Artifact.
    # Created node task has extra_data.project_id.
```

Run:

```bash
pytest test/test_workflow_standard_artifact_bindings.py -q
cd frontend && npm test -- preflight.spec.ts
```

Expected: fail only where workflow projectless/default context is not normalized.

**Step 2: Keep workflow using ArtifactVersion bindings**

Workflow upstream outputs should continue using `input_bindings`, not `standard_input_uploads`, because upstream nodes produce persisted Standard Artifacts.

Ensure `TaskCreate(project_id=run.project_id, input_bindings=...)` works when `run.project_id` is absent by resolving default project before scheduling Standard-output nodes.

**Step 3: Improve preflight messages**

In `preflight.ts`, distinguish:

- missing workflow boundary input
- waiting upstream Standard Artifact
- invalid semantic edge
- existing ArtifactVersion selection requiring project context

**Step 4: Run tests**

```bash
pytest test/test_workflow_standard_artifact_bindings.py test/test_workflow_definitions_api.py -q
cd frontend && npm test -- preflight.spec.ts useWorkflowPersistence.spec.ts
```

Expected: pass.

**Step 5: Commit**

```bash
git add backend/app/services/workflow_scheduler.py backend/app/services/workflow_runs.py \
  frontend/src/workflow/preflight.ts test/test_workflow_standard_artifact_bindings.py \
  frontend/src/workflow/preflight.spec.ts
git commit -m "fix: preserve workflow standard artifact auto binding"
```

### Task 8: Full Verification and Service Restart

**Files:**
- No source edits unless verification fails.

**Step 1: Run backend regression suite**

```bash
pytest test/test_tasks_service_standard_inputs.py \
  test/test_standard_execution_request_builder.py \
  test/test_tool_contracts.py \
  test/test_workflow_standard_artifact_bindings.py \
  test/test_workflow_definitions_api.py \
  test/test_workflow_persistence_api.py -q
```

Expected: pass.

**Step 2: Run frontend regression suite**

```bash
cd frontend && npm test -- \
  standard-artifact-run-context.spec.ts \
  standard-artifact-inputs.spec.ts \
  useStandaloneNodeRun.spec.ts \
  WorkflowNodeRunPanel.spec.ts \
  useWorkflowPersistence.spec.ts \
  preflight.spec.ts
```

Expected: pass.

**Step 3: Build**

```bash
cd frontend && npm run build
python -m compileall backend/app/tasks/standard_inputs.py backend/app/tasks/service.py \
  backend/app/execution/request_builder.py backend/app/execution/standard_contracts.py
git diff --check
```

Expected: build succeeds; existing Vite chunk warnings are acceptable if unchanged.

**Step 4: Restart local services**

```bash
ps -ef | rg 'uvicorn app.main|vite|npm run dev' | rg -v rg
kill <backend-and-frontend-pids>
cd backend && nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > ../logs/backend-dev.log 2>&1 &
cd frontend && nohup npm run dev -- --host 0.0.0.0 --port 8585 > ../logs/frontend-dev.log 2>&1 &
curl -s -o /tmp/sciminer_system_health.txt -w '%{http_code}' http://localhost:8000/api/v1/system/health
curl -s -o /tmp/sciminer_frontend.txt -w '%{http_code}' http://localhost:8585/
```

Expected: both return `200`.

**Step 5: Final commit if needed**

If verification required small fixes, commit them atomically:

```bash
git add <changed-files>
git commit -m "fix: verify standard artifact run context"
```

Expected: no unrelated dirty files staged.
