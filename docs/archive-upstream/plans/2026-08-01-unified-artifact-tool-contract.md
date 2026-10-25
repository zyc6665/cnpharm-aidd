# Unified Artifact Tool Contract Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a fixed platform-side artifact and tool contract so model tools adapt to the platform through package adapters instead of requiring platform-specific field mappings.

**Architecture:** Introduce a versioned standard Artifact registry, request/result envelopes, and multi-file ArtifactVersion persistence before wiring the worker, Agent, workflow, and frontend to consume derived contracts. Keep legacy `ToolVersion.config` and `agent_capability` running as compatibility paths while making Tool Package + standard Artifact the only new-tool path.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Alembic, Pydantic, pytest, Vue 3, TypeScript, existing Tool Package loader and AIDD workflow modules.

---

## Task 1: Add Standard Artifact Registry

**Files:**

- Create: `backend/app/artifact_standards/__init__.py`
- Create: `backend/app/artifact_standards/registry.py`
- Create: `backend/app/artifact_standards/schemas/protein_structure.v1.yaml`
- Create: `backend/app/artifact_standards/schemas/binding_pocket.v1.yaml`
- Create: `backend/app/artifact_standards/schemas/molecule_table.v1.yaml`
- Create: `backend/app/artifact_standards/schemas/ligand_structure.v1.yaml`
- Create: `backend/app/artifact_standards/schemas/run_report.v1.yaml`
- Create: `backend/app/artifact_standards/schemas/relations.yaml`
- Test: `test/test_artifact_standard_registry.py`

**Step 1: Write failing registry tests**

Cover:

- Registry loads the five MVP standard types.
- `binding_pocket@1` requires `residue_pocket_pdb`, `atom_pocket_pdb`, and `pocket_metadata_json`.
- Relation registry allows `derived_from`, `contains`, `describes`, `ranked_by`, `validated_by`, `visualized_by`.
- Unknown type, unknown version, and legacy alias are rejected for new standard contracts.

Run:

```bash
pytest test/test_artifact_standard_registry.py -q
```

Expected: fail because module does not exist.

**Step 2: Implement registry models and loader**

Use Pydantic models in `registry.py`:

- `StandardArtifactRef(type: str, version: int)`
- `FileRoleSpec(role, required, allowed_formats, content_types, primary)`
- `StandardArtifactSpec(type, version, file_roles, metadata_schema, validators)`
- `RelationSpec(type, description)`

Provide:

- `parse_standard_ref("binding_pocket@1")`
- `load_standard_artifact_specs()`
- `get_standard_artifact_spec("binding_pocket@1")`
- `is_standard_artifact_ref(value)`
- `load_relation_specs()`
- `validate_relation_type(value)`

Do not reuse `backend/app/services/semantic_types.py` in this new module except in later legacy migration.

**Step 3: Add YAML specs**

Keep files intentionally small. Example for `binding_pocket.v1.yaml`:

```yaml
type: binding_pocket
version: 1
file_roles:
  - role: residue_pocket_pdb
    required: true
    primary: true
    allowed_formats: [pdb]
    content_types: [chemical/x-pdb, chemical/x-pdbqt, application/octet-stream]
  - role: atom_pocket_pdb
    required: true
    allowed_formats: [pdb]
  - role: pocket_metadata_json
    required: true
    allowed_formats: [json]
metadata_schema:
  required: [center, bbox, residue_ids, atom_ids, source_protein_ref]
validators:
  - binding_pocket_v1_core
```

**Step 4: Run focused tests**

```bash
pytest test/test_artifact_standard_registry.py -q
```

Expected: pass.

## Task 2: Define Request v1 and Result v2 Contracts

**Files:**

- Create: `backend/app/execution/standard_contracts.py`
- Test: `test/test_standard_execution_contracts.py`

**Step 1: Write failing contract tests**

Cover:

- Request inputs are keyed by manifest input name.
- Request input file roles are preserved.
- Result artifact keys must match declared output names.
- `cardinality: many` output accepts a list.
- Result rejects absolute paths and `..` paths.
- Result rejects artifact type aliases such as `pocket_pdb`.

Run:

```bash
pytest test/test_standard_execution_contracts.py -q
```

Expected: fail because module does not exist.

**Step 2: Implement Pydantic models**

Add models:

- `StandardFileRef`
- `StandardInputArtifact`
- `StandardExecutionRequest`
- `StandardOutputFile`
- `StandardOutputArtifact`
- `StandardExecutionResult`
- `StandardRelationDeclaration`

Keep these models executor-neutral and free of ORM imports.

**Step 3: Add validation helpers**

Provide:

- `validate_result_against_declared_outputs(result, declared_outputs)`
- `iter_declared_output_artifacts(result, declared_outputs)`
- `safe_output_relative_path(path)`

Declared outputs can be simple typed dicts or small dataclasses in this phase. Do not require Tool Package v2 yet.

**Step 4: Run focused tests**

```bash
pytest test/test_standard_execution_contracts.py -q
```

Expected: pass.

## Task 3: Add Result v2 Parser and Hash Verification

**Files:**

- Create: `backend/app/execution/result_parser.py`
- Test: `test/test_standard_result_parser.py`

**Step 1: Write failing parser tests**

Use `tmp_path` to create output files. Cover:

- Parser reads `output/result.json`.
- Parser recomputes sha256 and accepts matching files.
- Parser rejects sha256 mismatch.
- Parser rejects missing required file role.
- Parser rejects output path escaping `output_dir`.
- Parser returns a normalized in-memory representation with artifact output name, type, file role, path, content type, and sha256.

Run:

```bash
pytest test/test_standard_result_parser.py -q
```

Expected: fail because parser does not exist.

**Step 2: Implement parser**

Function:

```python
def parse_standard_result(
    *,
    result_path: Path,
    output_dir: Path,
    declared_outputs: Sequence[DeclaredOutput],
) -> ParsedStandardResult:
    ...
```

The parser must use `artifact_standards.registry` to validate standard type refs and required file roles.

**Step 3: Run focused tests**

```bash
pytest test/test_standard_result_parser.py -q
```

Expected: pass.

## Task 4: Extend Tool Package Schema to v2

**Files:**

- Modify: `backend/app/tool_packages/schemas.py`
- Modify: `backend/app/tool_packages/validator.py`
- Modify: `backend/app/tool_packages/loader.py` if version branching is needed
- Test: `test/test_tool_package_v2_contract.py`

**Step 1: Write failing Tool Package v2 tests**

Cover:

- v2 manifest accepts `type: protein_structure@1` on inputs.
- v2 manifest accepts `cardinality: one | many` on outputs.
- v2 manifest rejects legacy `semantic_type` / `artifact_type` for new packages.
- v2 manifest rejects unknown standard type.
- v2 manifest rejects `device` as a required business parameter when it is only execution resource configuration.
- v1 package tests still pass unchanged.

Run:

```bash
pytest test/test_tool_package_v2_contract.py test/test_tool_package_contract.py -q
```

Expected: new tests fail.

**Step 2: Add v2 schema models**

Keep existing v1 models intact. Add:

- `ToolPackageV2Manifest`
- `ArtifactInputV2`
- `ArtifactOutputV2`
- `AdapterDeclaration`
- `ExposureDeclaration`

Support both `aidd.sciminer/v1` and `aidd.sciminer/tool-package.v2` in loader.

**Step 3: Validate against standard registry**

In validator:

- Ensure input/output `type` exists in standard registry.
- Ensure output cardinality is valid.
- Ensure relation types are from whitelist if declared.
- Ensure deployment infrastructure fields are absent from Tool Package v2.

**Step 4: Run focused tests**

```bash
pytest test/test_tool_package_v2_contract.py test/test_tool_package_contract.py -q
```

Expected: pass.

## Task 5: Add Multi-File Artifact Persistence

**Files:**

- Modify: `backend/app/models/artifacts.py`
- Create: `backend/alembic/versions/20260801_01_standard_artifact_versions.py`
- Modify: `backend/app/schemas/artifacts.py`
- Test: `test/test_standard_artifact_models.py`

**Step 1: Write failing model tests**

Cover SQLite metadata creation and relationships:

- `Artifact.standard_type` and `Artifact.standard_version` are available.
- `ArtifactVersion.manifest_json`, `summary_json`, `metrics_json`, `validation_status`, `validation_errors` are available.
- `ArtifactVersionFile` maps role -> file_id.
- A version can have multiple files.

Run:

```bash
pytest test/test_standard_artifact_models.py -q
```

Expected: fail.

**Step 2: Implement ORM changes**

Add fields without removing old columns yet:

- `Artifact.standard_type`
- `Artifact.standard_version`
- `Artifact.source_task_id`
- `ArtifactVersion.validation_status`
- `ArtifactVersion.validation_errors`
- `ArtifactVersion.manifest_json`
- `ArtifactVersion.summary_json`
- `ArtifactVersion.metrics_json`

Add new model:

- `ArtifactVersionFile`

Keep existing single-file fields on `ArtifactVersion` for compatibility until all APIs are migrated.

**Step 3: Add Alembic migration**

Migration should be additive and idempotent where existing project style uses table inspection.

**Step 4: Run model tests**

```bash
pytest test/test_standard_artifact_models.py -q
```

Expected: pass.

## Task 6: Create Standard Artifact Persistence Service

**Files:**

- Create: `backend/app/services/standard_artifacts.py`
- Test: `test/test_standard_artifact_service.py`

**Step 1: Write failing service tests**

Cover:

- Persist parsed `binding_pocket@1` output as one logical ArtifactVersion with three file roles.
- Persist `cardinality: many` ligand outputs as multiple ArtifactVersion records.
- Create `ArtifactLineage` or relation records for declared relations.
- Reject invalid relation type.
- Store validation status and errors.

Run:

```bash
pytest test/test_standard_artifact_service.py -q
```

Expected: fail.

**Step 2: Implement service**

Add:

```python
async def create_artifact_versions_from_parsed_result(
    db: AsyncSession,
    *,
    task: Task,
    parsed_result: ParsedStandardResult,
) -> StandardArtifactPersistenceResult:
    ...
```

Reuse existing `files` rows created by executors where possible. If the parser runs before file collection,
accept a file collector dependency so tests can use in-memory records.

**Step 3: Run focused tests**

```bash
pytest test/test_standard_artifact_service.py -q
```

Expected: pass.

## Task 7: Stage Standard Artifact Inputs into Request v1

**Files:**

- Create: `backend/app/execution/request_builder.py`
- Modify: `backend/app/tasks/executors/base.py` only if common staging helpers are needed
- Test: `test/test_standard_request_builder.py`

**Step 1: Write failing request builder tests**

Cover:

- Given `inputs.name -> artifact_version_id`, builder stages all file roles.
- Request uses manifest input name, not standard type as key.
- Same standard type can be bound to two different input names.
- Missing required input fails before runner starts.

Run:

```bash
pytest test/test_standard_request_builder.py -q
```

Expected: fail.

**Step 2: Implement request builder**

Function:

```python
async def build_standard_execution_request(
    db: AsyncSession,
    *,
    task: Task,
    tool_package_manifest: ToolPackageV2Manifest,
    input_bindings: dict[str, str],
    parameters: dict[str, Any],
    work_dir: Path,
    execution_context: ExecutionContext,
) -> StandardExecutionRequest:
    ...
```

Copy files into deterministic directories such as `input/<input_name>/<role_filename>`.

**Step 3: Run tests**

```bash
pytest test/test_standard_request_builder.py -q
```

Expected: pass.

## Task 8: Wire Standard Result Parsing into Worker Path

**Files:**

- Modify: `backend/app/worker/tasks.py`
- Modify: `backend/app/tasks/executors/ssh_job.py`
- Modify: `backend/app/tasks/executors/python_script.py`
- Modify: `backend/app/tasks/executors/docker.py`
- Test: `test/test_worker_standard_artifact_outputs.py`

**Step 1: Write failing worker integration tests**

Cover:

- A standard result creates ArtifactVersion records.
- `TaskOutput.file_ids` remains populated for compatibility.
- Standard artifact IDs are recorded in `TaskOutput.result` or a structured compatible field.
- Legacy result path still works.

Run:

```bash
pytest test/test_worker_standard_artifact_outputs.py test/test_worker_task_input_binding.py -q
```

Expected: new tests fail.

**Step 2: Add standard result detection**

Detect `result_version == "aidd.sciminer/result.v2"` and current tool package v2 manifest. If present:

- Parse and validate result.
- Collect files with file role metadata.
- Create ArtifactVersion records.
- Keep legacy `file_ids`.

If absent, keep current `prepare_task_output` behavior.

**Step 3: Run focused tests**

```bash
pytest test/test_worker_standard_artifact_outputs.py test/test_worker_task_input_binding.py -q
```

Expected: pass.

## Task 9: Derive ToolContract from Tool Package v2

**Files:**

- Modify: `backend/app/services/tool_contracts.py`
- Modify: `backend/app/agents/aidd/registry.py`
- Test: `test/test_tool_contracts.py`
- Test: `test/test_aidd_agent_registry.py`

**Step 1: Write failing contract tests**

Cover:

- v2 package produces contract inputs with `{name, type, cardinality}`.
- v2 package produces contract outputs with `{name, type, cardinality}`.
- Agent summary derives from v2 manifest without `agent_capability`.
- v2 package with `exposure.agent=false` is hidden from Agent but still direct-runnable if direct_run is true.
- Legacy config-based capability still works.

Run:

```bash
pytest test/test_tool_contracts.py test/test_aidd_agent_registry.py -q
```

Expected: new assertions fail.

**Step 2: Extend ToolContract shape compatibly**

Add under contract:

```python
"artifacts": {
    "inputs": [...],
    "outputs": [...],
}
"exposure": {...}
```

Keep legacy `capability` field for old Agent callers until frontend and planner migrate.

**Step 3: Update Agent registry discovery**

Prefer v2 package `artifacts` over DB `tool_capabilities` or config `agent_capability`.

**Step 4: Run tests**

```bash
pytest test/test_tool_contracts.py test/test_aidd_agent_registry.py -q
```

Expected: pass.

## Task 10: Update Agent Plan and Workflow Validation

**Files:**

- Modify: `backend/app/agents/aidd/plan_schema.py`
- Modify: `backend/app/agents/aidd/planner.py`
- Modify: `backend/app/agents/aidd/workflow_drafts.py`
- Modify: `backend/app/services/workflow_validation.py`
- Modify: `backend/app/services/workflow_scheduler.py`
- Test: `test/test_aidd_agent_planner.py`
- Test: `test/test_aidd_workflow_drafts.py`
- Test: `test/test_workflow_validation_standard_artifacts.py`

**Step 1: Write failing validation tests**

Cover:

- Plan binds input slot name to ArtifactVersion ID.
- Type/version must strictly match.
- Same standard type can satisfy multiple named inputs only when explicitly bound.
- LLM plan cannot execute if a required input slot is missing.
- Legacy workflow definitions still validate through compatibility path.

Run:

```bash
pytest test/test_aidd_agent_planner.py test/test_aidd_workflow_drafts.py test/test_workflow_validation_standard_artifacts.py -q
```

Expected: new tests fail.

**Step 2: Add standard slot validation**

Introduce helpers that validate:

```text
tool input slot -> ArtifactVersion.standard_type/version
tool output slot -> declared type/version
```

Do not remove old `semantic_inputs` yet. Add new fields such as `artifact_inputs` and `artifact_outputs`
to workflow node state where needed.

**Step 3: Run focused tests**

```bash
pytest test/test_aidd_agent_planner.py test/test_aidd_workflow_drafts.py test/test_workflow_validation_standard_artifacts.py -q
```

Expected: pass.

## Task 11: Add Protein Structure Importer

**Files:**

- Create: `backend/app/services/artifact_importers.py`
- Modify: `backend/app/api/v1/artifacts.py` or add a new endpoint if cleaner
- Test: `test/test_protein_structure_importer.py`

**Step 1: Write failing importer tests**

Cover:

- User uploaded PDB becomes `protein_structure@1`.
- Metadata JSON is generated.
- Invalid PDB fails validation.
- Importer creates file roles `structure_file` and `metadata_json`.

Run:

```bash
pytest test/test_protein_structure_importer.py -q
```

Expected: fail.

**Step 2: Implement minimal PDB metadata parser**

Keep MVP parser simple:

- Count `ATOM` / `HETATM` records.
- Extract chain IDs.
- Count residue identifiers.
- Preserve source filename.

Avoid adding RDKit or BioPython unless already present and needed.

**Step 3: Run tests**

```bash
pytest test/test_protein_structure_importer.py -q
```

Expected: pass.

## Task 12: Create LVpocket v2 Package Example

**Files:**

- Create: `example/LVpocket/tool-package-v2/tool.yaml`
- Create: `example/LVpocket/tool-package-v2/schemas/parameters.schema.json`
- Create: `example/LVpocket/tool-package-v2/schemas/result.v2.example.json`
- Modify or create adapter files under `example/LVpocket/tool-package-v2/runner/`
- Test: `test/test_lvpocket_tool_package_v2.py`

**Step 1: Write failing package tests**

Cover:

- Manifest validates as Tool Package v2.
- Golden result validates as `binding_pocket@1`.
- Required file roles are present.

Run:

```bash
pytest test/test_lvpocket_tool_package_v2.py -q
```

Expected: fail.

**Step 2: Add package files**

Use adapter stubs if real LVpocket execution is not available in CI. The contract test should validate the
package and golden output, not require remote SSH execution.

**Step 3: Run tests**

```bash
pytest test/test_lvpocket_tool_package_v2.py -q
```

Expected: pass.

## Task 13: Create Pocket2Mol v2 Package Example

**Files:**

- Create: `example/pocket2mol/tool-package-v2/tool.yaml`
- Create: `example/pocket2mol/tool-package-v2/schemas/parameters.schema.json`
- Create: `example/pocket2mol/tool-package-v2/schemas/result.v2.example.json`
- Test: `test/test_pocket2mol_tool_package_v2.py`

**Step 1: Write failing package tests**

Cover:

- Manifest consumes `binding_pocket@1`.
- Manifest outputs `molecule_table@1` and `ligand_structure@1` with `cardinality: many`.
- Golden result declares `contains` relations between molecule table and ligand structures.

Run:

```bash
pytest test/test_pocket2mol_tool_package_v2.py -q
```

Expected: fail.

**Step 2: Add package files and golden result**

Keep output small with two ligand examples.

**Step 3: Run tests**

```bash
pytest test/test_pocket2mol_tool_package_v2.py -q
```

Expected: pass.

## Task 14: Update Frontend Workflow Surface

**Files:**

- Modify: `frontend/src/workflow/contract-bindings.ts`
- Modify: `frontend/src/workflow/workflow-definitions.ts`
- Modify: `frontend/src/components/workflow/NodeEdgePanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowNodeInspector.vue`
- Modify: `frontend/src/components/workflow/WorkflowRunInputPanel.vue`
- Test: `frontend/test/workflow-contract-bindings.test.ts`
- Test: `frontend/test/workflow-node-inspector-surface.test.ts`

**Step 1: Write failing frontend tests**

Cover:

- UI derives input slots from standard artifact contract.
- UI shows `protein: protein_structure@1` instead of semantic mapping rows.
- Run input panel asks for ArtifactVersion compatible with slot type.
- Legacy semantic mapping still renders for legacy nodes.

Run:

```bash
cd frontend && npm test -- workflow-contract-bindings workflow-node-inspector-surface
```

Expected: fail.

**Step 2: Implement standard slot display**

Add standard contract parsing without removing legacy functions. Keep names clear:

- `ArtifactInputSlot`
- `ArtifactOutputSlot`
- `deriveArtifactSlotsFromToolContract`

**Step 3: Run focused tests**

```bash
cd frontend && npm test -- workflow-contract-bindings workflow-node-inspector-surface
```

Expected: pass.

## Task 15: Update Tool Creation UI for New Path

**Files:**

- Modify: `frontend/src/views/tools/Create.vue`
- Modify: `frontend/src/api/tools.ts`
- Modify: `frontend/src/views/tools/detail-schema.ts`
- Test: `frontend/test/tool-create-page-polish.test.ts`
- Test: `frontend/test/tool-detail-schema.test.ts`

**Step 1: Write failing UI tests**

Cover:

- New tool creation prefers Tool Package upload/register path.
- Legacy `input_schema/output_schema/agent_capability` fields are marked legacy.
- New Tool Package tools do not show Agent semantic mapping editor.

Run:

```bash
cd frontend && npm test -- tool-create-page-polish tool-detail-schema
```

Expected: fail.

**Step 2: Implement UI transition**

Keep old editor available for legacy tools only. Do not remove old fields yet.

**Step 3: Run focused tests**

```bash
cd frontend && npm test -- tool-create-page-polish tool-detail-schema
```

Expected: pass.

## Task 16: Add Legacy Migration Helpers

**Files:**

- Create: `backend/app/tool_packages/legacy_migration.py`
- Modify: `backend/app/services/semantic_types.py` only if alias map should be reused from there
- Test: `test/test_tool_package_legacy_migration.py`

**Step 1: Write failing migration tests**

Cover:

- `protein_pdb` and `protein_structure` map to `protein_structure@1`.
- `pocket_pdb` and `pocket_result` map to `binding_pocket@1`.
- `generated_ligand` maps to explicit output choice, not silently to both molecule table and ligand.
- New v2 validator rejects aliases outside migration.

Run:

```bash
pytest test/test_tool_package_legacy_migration.py -q
```

Expected: fail.

**Step 2: Implement migration helper**

Return a migration draft and warnings; do not silently publish migrated packages.

**Step 3: Run tests**

```bash
pytest test/test_tool_package_legacy_migration.py -q
```

Expected: pass.

## Task 17: Run Integration and Regression Suite

**Files:**

- No new files unless test failures require targeted fixes.

**Step 1: Run backend focused suites**

```bash
pytest test/test_artifact_standard_registry.py \
  test/test_standard_execution_contracts.py \
  test/test_standard_result_parser.py \
  test/test_tool_package_v2_contract.py \
  test/test_standard_artifact_models.py \
  test/test_standard_artifact_service.py \
  test/test_standard_request_builder.py \
  test/test_worker_standard_artifact_outputs.py \
  test/test_tool_contracts.py \
  test/test_aidd_agent_registry.py \
  test/test_aidd_workflow_drafts.py -q
```

Expected: pass.

**Step 2: Run existing backend regression tests around touched systems**

```bash
pytest test/test_tool_package_contract.py \
  test/test_tool_import_api.py \
  test/test_worker_task_input_binding.py \
  test/test_workflow_persistence_api.py \
  test/test_aidd_agent_registry.py \
  test/test_typed_artifacts_api.py -q
```

Expected: pass.

**Step 3: Run frontend focused tests**

```bash
cd frontend && npm test -- workflow-contract-bindings workflow-node-inspector-surface tool-detail-schema
```

Expected: pass.

**Step 4: Run build checks**

```bash
cd frontend && npm run build
pytest test -q
```

Expected: pass.

## Implementation Notes

- Do not remove legacy `semantic_inputs`, `semantic_outputs`, `agent_capability`, or `TaskOutput.file_ids` in the MVP.
- Do not add runtime quality/constraints selection logic to Agent.
- Do not store deployment profile host credentials in Tool Package manifests.
- Keep standard registry source in code-controlled files, not admin-editable database rows.
- Avoid large frontend rewrites. Add standard Artifact slot support beside existing semantic mapping support, then hide legacy editors for new package tools.
- Follow TDD for each task: failing test first, minimal implementation, focused pass, regression pass.

## Handoff

Plan complete and saved to `docs/plans/2026-08-01-unified-artifact-tool-contract.md`.

Recommended execution path: start with Tasks 1-3 only. They are pure contract and parser work, isolated from database and UI churn, and will prove the standard shape before deeper integration.
