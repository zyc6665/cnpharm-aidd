# Workflow Artifact Binding Resolver Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a backend-authoritative Artifact Binding Resolver so workflow edges and standalone node runs bind standard ArtifactVersion roles, not just broad semantic file IDs.

**Architecture:** Add a deep backend module that resolves target tool input requirements against candidate ArtifactVersions and returns a deterministic binding decision. Keep current standard Artifact types, extend tool input declarations with role/readiness requirements, and project resolved decisions into legacy `file_ids` / `input_files` only at executor submission time. Frontend preflight and node panels consume backend decisions or a mirrored lightweight shape for display, but backend scheduling remains authoritative.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, SQLite/Postgres-compatible models, Vue 3, Pinia, Vitest, pytest.

---

### Task 1: Add Backend Resolver Types

**Files:**
- Create: `backend/app/services/artifact_binding_resolver.py`
- Test: `backend/test/test_artifact_binding_resolver.py`

**Step 1: Write the failing tests**

Create tests for pure policy decisions using small in-memory records or minimal factories:

```python
def test_raw_protein_needs_preparation_when_policy_requires_prepared():
    decision = resolve_artifact_binding_policy(
        input_slot={
            "name": "protein",
            "type": "protein_structure@1",
            "role_preferences": ["prepared_pdb", "structure_file"],
            "readiness_policy": "require_prepared",
            "suggested_preparation_tool": "builtin-protein-preparation",
        },
        artifact_type="protein_structure@1",
        available_roles={"structure_file"},
        metadata={"preparation_status": "raw"},
    )

    assert decision.status == "needs_preparation"
    assert decision.suggested_tool_slug == "builtin-protein-preparation"
```

Add tests for:

- prepared protein selects `prepared_pdb`.
- receptor policy selects `receptor_pdbqt`.
- ligand 3D policy selects `structure_3d_sdf`.
- only ligand 2D returns `needs_conversion`.
- standard type mismatch returns `invalid`.

**Step 2: Run tests to verify they fail**

Run: `pytest backend/test/test_artifact_binding_resolver.py -q`

Expected: FAIL because `artifact_binding_resolver.py` does not exist.

**Step 3: Implement resolver dataclasses and pure policy function**

Implement:

```python
@dataclass(frozen=True)
class ArtifactBindingDecision:
    status: Literal["ready", "needs_preparation", "needs_conversion", "invalid"]
    input_name: str
    standard_type: str
    selected_role: str | None = None
    selected_file_id: str | None = None
    artifact_version_id: str | None = None
    reason: str = ""
    suggested_tool_slug: str | None = None


def resolve_artifact_binding_policy(*, input_slot, artifact_type, available_roles, metadata):
    ...
```

Keep this function database-free so it is easy to test.

**Step 4: Run tests to verify they pass**

Run: `pytest backend/test/test_artifact_binding_resolver.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/artifact_binding_resolver.py backend/test/test_artifact_binding_resolver.py
git commit -m "feat: add artifact binding resolver policy"
```

### Task 2: Resolve ArtifactVersion Roles From Database

**Files:**
- Modify: `backend/app/services/artifact_binding_resolver.py`
- Test: `backend/test/test_artifact_binding_resolver.py`

**Step 1: Write the failing tests**

Add async tests that create:

- one `Artifact` with `standard_type='protein_structure'` and `standard_version=1`.
- one `ArtifactVersion` with `manifest_json.metadata.preparation_status='prepared'`.
- `ArtifactVersionFile` rows for `structure_file` and `prepared_pdb`.

Assert:

```python
decision = await resolve_artifact_binding(
    db,
    input_slot={"name": "protein", "type": "protein_structure@1", "readiness_policy": "require_prepared"},
    candidate_artifact_version_id=version.id,
)
assert decision.status == "ready"
assert decision.selected_role == "prepared_pdb"
assert decision.selected_file_id == prepared_file.id
```

**Step 2: Run tests to verify they fail**

Run: `pytest backend/test/test_artifact_binding_resolver.py -q`

Expected: FAIL because async DB resolver is not implemented.

**Step 3: Implement async DB resolver**

Load `ArtifactVersion` with `ArtifactVersion.files.file` and `ArtifactVersion.artifact`, derive:

- `artifact_type` from `Artifact.standard_type@standard_version` or manifest `type`.
- `available_roles` from `ArtifactVersionFile.role`.
- `metadata` from `ArtifactVersion.manifest_json.metadata`.
- `role -> file_id` mapping from linked files.

Call the pure policy function, then attach `artifact_version_id` and selected `file_id`.

**Step 4: Run tests to verify they pass**

Run: `pytest backend/test/test_artifact_binding_resolver.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/artifact_binding_resolver.py backend/test/test_artifact_binding_resolver.py
git commit -m "feat: resolve artifact binding roles from database"
```

### Task 3: Extend Tool Contract Input Shape

**Files:**
- Modify: `backend/app/tool_packages/schemas.py`
- Modify: `backend/app/remote_tools/schemas.py`
- Modify: `backend/app/schemas/tools.py`
- Modify: `frontend/src/types/models.d.ts`
- Test: existing schema tests or add `backend/test/test_tool_contract_role_requirements.py`

**Step 1: Write the failing tests**

Add schema tests showing artifact inputs can carry:

```json
{
  "name": "protein",
  "type": "protein_structure@1",
  "required": true,
  "role_preferences": ["prepared_pdb", "structure_file"],
  "required_roles": [],
  "readiness_policy": "prefer_prepared_warn_raw",
  "suggested_preparation_tool": "builtin-protein-preparation"
}
```

**Step 2: Run tests to verify they fail**

Run: `pytest backend/test/test_tool_contract_role_requirements.py -q`

Expected: FAIL because extra fields are forbidden.

**Step 3: Implement schema fields**

Add optional fields to artifact input declarations only:

- `role_preferences: list[str] = []`
- `required_roles: list[str] = []`
- `readiness_policy: str | None = None`
- `suggested_preparation_tool: str | None = None`

Keep output declarations unchanged.

**Step 4: Update frontend types**

Extend `ToolContract.artifacts.inputs[]` with the same optional fields.

**Step 5: Run tests**

Run:

```bash
pytest backend/test/test_tool_contract_role_requirements.py -q
npm test -- src/workflow/contract-bindings.spec.ts
```

Expected: PASS.

**Step 6: Commit**

```bash
git add backend/app/tool_packages/schemas.py backend/app/remote_tools/schemas.py backend/app/schemas/tools.py frontend/src/types/models.d.ts backend/test/test_tool_contract_role_requirements.py
git commit -m "feat: allow role-aware artifact input contracts"
```

### Task 4: Update Protein and Ligand Tool Contracts

**Files:**
- Modify: `backend/app/services/aidd_builtin_tools.py`
- Modify: `backend/app/tool_templates/drug_discovery/vina-docking.yaml`
- Modify: `backend/app/tool_templates/drug_discovery/smina-docking.yaml`
- Modify: `backend/app/tool_templates/drug_discovery/ligand-preparation.yaml`
- Modify: any LVpocket seed/template file if present; otherwise add migration or admin seed update for `lvpocket-pocket-prediction`.
- Test: `backend/test/test_artifact_binding_resolver.py`

**Step 1: Write the failing tests**

Add assertions that builtin/tool-template artifact inputs expose policies:

- `builtin-protein-preparation` accepts raw protein.
- LVpocket prefers prepared protein.
- Vina/Smina require receptor PDBQT or receptor readiness.
- ligand preparation/conformer tools can satisfy docking ligand readiness.

**Step 2: Run tests to verify they fail**

Run: `pytest backend/test/test_artifact_binding_resolver.py -q`

Expected: FAIL because contracts do not declare role policies.

**Step 3: Add contract fields**

Use these v1 defaults:

- LVpocket: `role_preferences=['prepared_pdb', 'structure_file']`, `readiness_policy='prefer_prepared_warn_raw'`.
- Vina/Smina protein: `role_preferences=['receptor_pdbqt', 'prepared_pdb']`, `required_roles=['receptor_pdbqt']`, `readiness_policy='require_receptor'`.
- Docking ligand: `role_preferences=['structure_3d_sdf', 'structure_file']`, `readiness_policy='prefer_3d_ligand'`.

**Step 4: Run tests**

Run: `pytest backend/test/test_artifact_binding_resolver.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/aidd_builtin_tools.py backend/app/tool_templates/drug_discovery/vina-docking.yaml backend/app/tool_templates/drug_discovery/smina-docking.yaml backend/app/tool_templates/drug_discovery/ligand-preparation.yaml
git commit -m "feat: declare role-aware drug discovery inputs"
```

### Task 5: Wire Resolver Into Workflow Scheduling

**Files:**
- Modify: `backend/app/services/workflow_scheduler.py`
- Test: `backend/test/test_workflow_artifact_binding_scheduler.py`

**Step 1: Write the failing tests**

Create a workflow where:

- node A outputs raw `protein_structure@1` from `builtin-fetch-pdb`.
- node B is a tool requiring prepared protein.
- node B has `artifact_inputs={'protein': 'node:fetch:protein'}`.

Assert scheduling node B does not create a task and node state gets:

```python
{
  "status": "blocked",
  "binding_decisions": {"protein": {"status": "needs_preparation"}}
}
```

Also test prepared upstream schedules successfully and `input_file_ids` contains the selected `prepared_pdb` file only.

**Step 2: Run tests to verify they fail**

Run: `pytest backend/test/test_workflow_artifact_binding_scheduler.py -q`

Expected: FAIL because scheduler only checks file IDs.

**Step 3: Implement scheduler integration**

In `resolve_node_input_files` or a new helper, when resolving `artifact_inputs`, use `resolve_artifact_binding` if the source is a standard Artifact output. If decision is not `ready`, return a blocked decision and avoid task creation.

Store decisions in node state for UI consumption.

**Step 4: Run tests**

Run:

```bash
pytest backend/test/test_workflow_artifact_binding_scheduler.py -q
pytest backend/test/test_workflow_scheduler.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/workflow_scheduler.py backend/test/test_workflow_artifact_binding_scheduler.py
git commit -m "feat: gate workflow nodes on artifact binding readiness"
```

### Task 6: Wire Resolver Into Standalone Node Runs

**Files:**
- Modify: `backend/app/api/v1/tasks.py` or relevant task creation route.
- Modify: `frontend/src/composables/useStandaloneNodeRun.ts`
- Modify: `frontend/src/components/workflow/WorkflowNodeRunPanel.vue`
- Test: `frontend/src/components/workflow/WorkflowNodeRunPanel.spec.ts`
- Test: backend task API test covering input bindings.

**Step 1: Write failing tests**

Frontend test: selected upstream standard artifact recommendation should submit `input_bindings` when ArtifactVersion metadata is available, not only `file_ids`.

Backend test: standalone task creation with input binding and legacy `ssh_job` field projects selected role into `params.input_files.protein_pdb`.

**Step 2: Run tests to verify they fail**

Run:

```bash
npm test -- src/components/workflow/WorkflowNodeRunPanel.spec.ts
pytest backend/test/test_tasks_artifact_binding.py -q
```

Expected: FAIL because standalone run still mainly submits file IDs.

**Step 3: Implement standalone resolver path**

- Preserve manual uploads as legacy files.
- For selected standard artifacts, submit `input_bindings` keyed by slot name when possible.
- Backend validates binding through resolver and builds legacy payload only after role selection.

**Step 4: Run tests**

Run:

```bash
npm test -- src/components/workflow/WorkflowNodeRunPanel.spec.ts
pytest backend/test/test_tasks_artifact_binding.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/api/v1/tasks.py frontend/src/composables/useStandaloneNodeRun.ts frontend/src/components/workflow/WorkflowNodeRunPanel.vue frontend/src/components/workflow/WorkflowNodeRunPanel.spec.ts backend/test/test_tasks_artifact_binding.py
git commit -m "feat: resolve standalone node artifact bindings"
```

### Task 7: Surface Binding Decisions In Preflight UI

**Files:**
- Modify: `frontend/src/workflow/preflight.ts`
- Modify: `frontend/src/components/workflow/WorkflowPreflightPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowNodeRunPanel.vue`
- Test: `frontend/src/workflow/preflight.spec.ts`
- Test: `frontend/src/components/workflow/WorkflowPreflightPanel.spec.ts`

**Step 1: Write failing tests**

Add preflight issue types:

- `needs_preparation`
- `needs_conversion`
- `invalid_artifact_binding`

Assert raw PDB connected to prepared-required node renders a clear action-oriented message.

**Step 2: Run tests to verify they fail**

Run:

```bash
npm test -- src/workflow/preflight.spec.ts src/components/workflow/WorkflowPreflightPanel.spec.ts
```

Expected: FAIL because issue types and messages do not exist.

**Step 3: Implement UI issue display**

Use backend `binding_decisions` from run state when available. For not-yet-run canvas previews, use a lightweight mirror only for display; mark it as advisory.

**Step 4: Run tests**

Run:

```bash
npm test -- src/workflow/preflight.spec.ts src/components/workflow/WorkflowPreflightPanel.spec.ts
```

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/workflow/preflight.ts frontend/src/components/workflow/WorkflowPreflightPanel.vue frontend/src/components/workflow/WorkflowNodeRunPanel.vue frontend/src/workflow/preflight.spec.ts frontend/src/components/workflow/WorkflowPreflightPanel.spec.ts
git commit -m "feat: show workflow artifact binding readiness"
```

### Task 8: Full Verification

**Files:**
- No source changes unless failures require fixes.

**Step 1: Run backend tests**

Run:

```bash
pytest backend/test/test_artifact_binding_resolver.py backend/test/test_workflow_artifact_binding_scheduler.py backend/test/test_tasks_artifact_binding.py -q
```

Expected: PASS.

**Step 2: Run frontend tests**

Run:

```bash
npm test -- src/components/workflow/WorkflowNodeRunPanel.spec.ts src/workflow/preflight.spec.ts src/components/workflow/WorkflowPreflightPanel.spec.ts
```

Expected: PASS.

**Step 3: Run build checks**

Run:

```bash
cd frontend && npm run build
git diff --check
git status --short
```

Expected: build passes; diff check passes; only intended changes are present.

**Step 4: Final commit if needed**

Only commit verification fixes if any were required:

```bash
git add <fixed-files>
git commit -m "fix: harden workflow artifact binding readiness"
```
