# Protein Preparation Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a visible, runnable Protein Preparation node that turns raw `protein_structure@1` Artifacts into prepared downstream-ready protein Artifacts with prepared PDB/PDBQT roles.

**Architecture:** Treat protein preparation as a platform builtin tool with standard Artifact input/output slots, not as a hidden import side effect. The preparation engine sits behind a small backend module interface; board APIs create visible process nodes and schedule normal platform tasks; standard result.v2 persistence creates derived Artifact lineage. Workflow draft generation must respect explicit board edges so raw protein -> preparation -> downstream tools is preserved.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, existing Task/Workflow runtime, standard Artifact registry/result.v2 persistence, Vue 3, Pinia/workflow canvas utilities, Vitest, pytest.

---

## Context And Constraints

- Work in `/data/zhouyc/cpumodel_sciminer` on the current branch.
- Do not stage existing unrelated dirty files: deleted `AGENTS.md`, deleted docs, untracked `docs/需求文档/`, `func_detail/`, and `model/...` files.
- Follow TDD: write each regression test first, run it to confirm RED, implement, then re-run to confirm GREEN.
- Use frequent atomic commits. Ask for explicit confirmation before each `git commit` if the active session requires dangerous-operation confirmation.
- Preserve original imported protein Artifacts. Prepared proteins must be derived outputs with lineage, not overwrites.
- First UI exposes basic options only, but backend request schema must include `advanced_options` for later advanced mode.

---

### Task 1: Extend `protein_structure@1` Roles And Metadata

**Files:**
- Modify: `backend/app/artifact_standards/schemas/protein_structure.v1.yaml`
- Modify: `test/test_artifact_standard_registry.py`

**Step 1: Write the failing test**

Add tests similar to the existing metadata schema tests:

```python
def test_protein_structure_declares_preparation_file_roles():
    spec = get_standard_artifact_spec("protein_structure@1")
    roles = {role.role: role for role in spec.file_roles}
    assert roles["structure_file"].primary is True
    assert roles["prepared_pdb"].required is False
    assert "pdb" in roles["prepared_pdb"].allowed_formats
    assert roles["receptor_pdbqt"].required is False
    assert "pdbqt" in roles["receptor_pdbqt"].allowed_formats
    assert roles["preparation_report_json"].required is False


def test_protein_structure_metadata_schema_declares_preparation_fields():
    spec = get_standard_artifact_spec("protein_structure@1")
    properties = spec.metadata_schema["properties"]
    assert properties["preparation_status"]["enum"] == ["raw", "prepared", "failed"]
    assert properties["preparation_profile"]["type"] == "string"
    assert properties["ph"]["type"] == "number"
    assert properties["remove_water"]["type"] == "boolean"
    assert properties["keep_metals"]["type"] == "boolean"
    assert properties["keep_cofactors"]["type"] == "boolean"
    assert properties["remove_non_target_ligands"]["type"] == "boolean"
    assert properties["preparation_engine"]["type"] == "string"
    assert properties["source_artifact_version_id"]["type"] == "string"
```

**Step 2: Run test to verify it fails**

Run:

```bash
pytest test/test_artifact_standard_registry.py -k "preparation" -q
```

Expected: FAIL because the new roles and metadata fields are absent.

**Step 3: Write minimal implementation**

Update `protein_structure.v1.yaml`:

```yaml
  - role: raw_structure_file
    required: false
    allowed_formats: [pdb, cif]
    content_types: [chemical/x-pdb, chemical/x-cif, application/octet-stream]
    recommended_name: raw_structure.pdb
  - role: prepared_pdb
    required: false
    allowed_formats: [pdb]
    content_types: [chemical/x-pdb, application/octet-stream]
    recommended_name: prepared.pdb
  - role: prepared_pqr
    required: false
    allowed_formats: [pqr]
    content_types: [chemical/x-pqr, text/plain, application/octet-stream]
    recommended_name: prepared.pqr
  - role: receptor_pdbqt
    required: false
    allowed_formats: [pdbqt]
    content_types: [chemical/x-pdbqt, application/octet-stream]
    recommended_name: receptor.pdbqt
  - role: preparation_report_json
    required: false
    allowed_formats: [json]
    content_types: [application/json]
    recommended_name: preparation_report.json
```

Add metadata fields under `properties` without adding new required fields.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest test/test_artifact_standard_registry.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/artifact_standards/schemas/protein_structure.v1.yaml test/test_artifact_standard_registry.py
git commit -m "feat: extend protein structure preparation roles"
```

---

### Task 2: Add Protein Preparation Request Schemas

**Files:**
- Create: `backend/app/schemas/protein_preparation.py`
- Create: `test/test_protein_preparation_schemas.py`

**Step 1: Write the failing test**

```python
from app.schemas.protein_preparation import ProteinPreparationRequest


def test_preparation_request_accepts_basic_options_and_advanced_extension():
    data = ProteinPreparationRequest.model_validate({
        "artifact_id": "artifact-1",
        "source_node_id": "artifact-node-1",
        "position": {"x": 320, "y": 120},
        "preparation_profile": "docking_v1",
        "options": {
            "ph": 7.4,
            "remove_water": True,
            "keep_metals": True,
            "keep_cofactors": True,
            "remove_non_target_ligands": True,
            "output_formats": ["prepared_pdb", "receptor_pdbqt"],
        },
        "advanced_options": {"chain_selection": ["A"]},
    })
    assert data.options.ph == 7.4
    assert data.advanced_options == {"chain_selection": ["A"]}


def test_preparation_request_rejects_unknown_output_format():
    with pytest.raises(ValidationError):
        ProteinPreparationRequest.model_validate({
            "artifact_id": "artifact-1",
            "preparation_profile": "docking_v1",
            "options": {"output_formats": ["mol2"]},
        })
```

**Step 2: Run test to verify it fails**

Run:

```bash
pytest test/test_protein_preparation_schemas.py -q
```

Expected: FAIL because `app.schemas.protein_preparation` does not exist.

**Step 3: Write minimal implementation**

Create Pydantic models:

```python
ProteinPreparationOutputFormat = Literal["prepared_pdb", "receptor_pdbqt", "prepared_pqr"]


class ProteinPreparationOptions(BaseModel):
    ph: float = Field(default=7.4, ge=0, le=14)
    remove_water: bool = True
    keep_metals: bool = True
    keep_cofactors: bool = True
    remove_non_target_ligands: bool = True
    output_formats: list[ProteinPreparationOutputFormat] = Field(
        default_factory=lambda: ["prepared_pdb", "receptor_pdbqt"]
    )


class ProteinPreparationRequest(BaseModel):
    artifact_id: str = Field(min_length=1, max_length=36)
    artifact_version_id: str | None = Field(default=None, min_length=1, max_length=36)
    source_node_id: str | None = Field(default=None, min_length=1, max_length=120)
    position: BoardPosition | None = None
    preparation_profile: Literal["docking_v1"] = "docking_v1"
    options: ProteinPreparationOptions = Field(default_factory=ProteinPreparationOptions)
    advanced_options: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="forbid")
```

**Step 4: Run test to verify it passes**

Run:

```bash
pytest test/test_protein_preparation_schemas.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/schemas/protein_preparation.py test/test_protein_preparation_schemas.py
git commit -m "feat: add protein preparation request schema"
```

---

### Task 3: Create Protein Preparation Engine Module

**Files:**
- Create: `backend/app/protein_preparation/__init__.py`
- Create: `backend/app/protein_preparation/engine.py`
- Create: `test/test_protein_preparation_engine.py`

**Step 1: Write the failing test**

Use a small PDB fixture with water and protein atom records. Mock external command execution so tests do not require PDBFixer, Meeko, or Open Babel installed locally.

```python
def test_prepare_protein_removes_water_and_returns_requested_roles(tmp_path, monkeypatch):
    source = tmp_path / "raw.pdb"
    source.write_text(
        "ATOM      1  N   ALA A   1       0.000   0.000   0.000\n"
        "HETATM    2  O   HOH A 101       1.000   1.000   1.000\n"
        "END\n"
    )

    def fake_convert(prepared_pdb: Path, receptor_pdbqt: Path, *, rigid: bool):
        receptor_pdbqt.write_text("REMARK receptor pdbqt\n")

    monkeypatch.setattr(engine, "convert_prepared_pdb_to_pdbqt", fake_convert)

    result = engine.prepare_protein(
        source,
        ProteinPreparationOptions(remove_water=True),
        advanced_options={"chain_selection": ["A"]},
        output_dir=tmp_path / "out",
    )

    assert "prepared_pdb" in result.files
    assert "receptor_pdbqt" in result.files
    assert "HOH" not in result.files["prepared_pdb"].path.read_text()
    assert result.report["options"]["ph"] == 7.4
    assert result.report["advanced_options"] == {"chain_selection": ["A"]}
```

**Step 2: Run test to verify it fails**

Run:

```bash
pytest test/test_protein_preparation_engine.py -q
```

Expected: FAIL because the engine module does not exist.

**Step 3: Write minimal implementation**

Create a deep module with this interface:

```python
@dataclass(frozen=True)
class PreparedProteinFile:
    role: str
    path: Path
    content_type: str


@dataclass(frozen=True)
class ProteinPreparationResult:
    files: dict[str, PreparedProteinFile]
    report: dict[str, Any]
    warnings: list[str]


def prepare_protein(
    source_path: Path,
    options: ProteinPreparationOptions,
    *,
    advanced_options: dict[str, Any] | None = None,
    output_dir: Path,
) -> ProteinPreparationResult:
    ...
```

Implementation notes:

- v1 must not claim full scientific protonation if required engines are unavailable.
- Keep water removal deterministic by filtering common water residues (`HOH`, `WAT`, `H2O`) when `remove_water=True`.
- Add hydrogens/protonation through the selected external engine when available; otherwise raise a clear `ProteinPreparationError` if the user requested formats that require it.
- Generate `prepared_pdb` before format conversion.
- Generate `receptor_pdbqt` via `convert_prepared_pdb_to_pdbqt(prepared_pdb, target, rigid=True)`.
- Always write report data in memory; later tasks write `preparation_report_json` into standard result.v2.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest test/test_protein_preparation_engine.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/protein_preparation test/test_protein_preparation_engine.py
git commit -m "feat: add protein preparation engine"
```

---

### Task 4: Support Standard result.v2 From Builtin Tools

**Files:**
- Modify: `backend/app/agents/aidd/builtin_tools.py`
- Modify: `backend/app/tasks/executors/builtin.py`
- Modify: `backend/app/services/standard_artifacts.py`
- Create or modify: `test/test_aidd_builtin_standard_artifacts.py`

**Step 1: Write the failing test**

Add a test proving a builtin result can return a standard result.v2 envelope and collected role files:

```python
def test_builtin_executor_returns_standard_result_v2(tmp_path, monkeypatch):
    result = BuiltinToolResult(
        standard_result={
            "result_version": "aidd.sciminer/result",
            "artifacts": {
                "prepared_protein": {
                    "type": "protein_structure@1",
                    "name": "Prepared Protein",
                    "files": {
                        "structure_file": {"path": "prepared.pdb", "sha256": "..."},
                        "prepared_pdb": {"path": "prepared.pdb", "sha256": "..."},
                        "receptor_pdbqt": {"path": "receptor.pdbqt", "sha256": "..."},
                    },
                }
            },
        },
        artifacts=(...),
    )
    # Assert BuiltinExecutor output_result["result"]["result_version"] is result.v2.
```

Use test-local fake hashes/files instead of real conversion.

**Step 2: Run test to verify it fails**

Run:

```bash
pytest test/test_aidd_builtin_standard_artifacts.py -q
```

Expected: FAIL because `BuiltinToolResult` has no `standard_result` support.

**Step 3: Write minimal implementation**

- Extend `BuiltinToolResult` with `standard_result: dict[str, Any] | None = None`.
- In `BuiltinExecutor.execute`, after writing `result.artifacts`, return `result.standard_result` as the primary `result` when present:

```python
output_data = result.standard_result if result.standard_result else {
    output.semantic_type: output.data for output in result.outputs
}
return {"success": True, "result": output_data, "output_file_ids": output_file_ids}
```

- Extend `standard_artifacts.py` declared-output discovery so builtin configs with `config["artifacts"]["outputs"]` participate in standard result.v2 persistence, not only Tool Package v2 and remote API v1.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest test/test_aidd_builtin_standard_artifacts.py test/test_worker_standard_artifact_outputs.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/agents/aidd/builtin_tools.py backend/app/tasks/executors/builtin.py backend/app/services/standard_artifacts.py test/test_aidd_builtin_standard_artifacts.py
git commit -m "feat: persist builtin standard artifacts"
```

---

### Task 5: Register `builtin-protein-preparation`

**Files:**
- Modify: `backend/app/agents/aidd/capabilities.py`
- Modify: `backend/app/agents/aidd/builtin_tools.py`
- Modify: `backend/app/services/aidd_builtin_tools.py`
- Modify: `test/test_aidd_agent_capabilities.py`
- Modify: `test/test_aidd_builtin_task_tools.py`

**Step 1: Write the failing test**

```python
def test_builtin_protein_preparation_capability_declares_standard_artifacts():
    capability = get_capability("builtin-protein-preparation")
    assert capability.capability == "protein_preparation"
    assert capability.stage == "protein_preparation"
```

Add a persisted-tool test:

```python
tool = await ensure_aidd_builtin_tool(..., tool_slug="builtin-protein-preparation")
config = tool.current_version.config
assert config["type"] == "builtin"
assert config["builtin_slug"] == "builtin-protein-preparation"
assert config["artifacts"]["inputs"] == [
    {"name": "protein", "type": "protein_structure@1", "required": True}
]
assert config["artifacts"]["outputs"] == [
    {"name": "prepared_protein", "type": "protein_structure@1", "required": True}
]
```

**Step 2: Run test to verify it fails**

Run:

```bash
pytest test/test_aidd_agent_capabilities.py test/test_aidd_builtin_task_tools.py -k "protein_preparation" -q
```

Expected: FAIL because the builtin is not registered.

**Step 3: Write minimal implementation**

- Add `builtin-protein-preparation` to `AIDD_TOOL_CAPABILITIES`.
- Extend `ToolCapability` only if needed with optional artifact slots; otherwise special-case `_capability_config` for this slug to include:

```python
"artifacts": {
    "inputs": [{"name": "protein", "type": "protein_structure@1", "required": True}],
    "outputs": [{"name": "prepared_protein", "type": "protein_structure@1", "required": True}],
}
```

- Add registry entry in `_BUILTIN_TOOL_REGISTRY` and dispatch handler key `protein_preparation`.
- Handler reads `files["protein_structure@1"]` first, then `files["protein"]` fallback.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest test/test_aidd_agent_capabilities.py test/test_aidd_builtin_task_tools.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/agents/aidd/capabilities.py backend/app/agents/aidd/builtin_tools.py backend/app/services/aidd_builtin_tools.py test/test_aidd_agent_capabilities.py test/test_aidd_builtin_task_tools.py
git commit -m "feat: register protein preparation builtin"
```

---

### Task 6: Implement Builtin Protein Preparation Handler

**Files:**
- Modify: `backend/app/agents/aidd/builtin_tools.py`
- Modify: `backend/app/protein_preparation/engine.py`
- Create or modify: `test/test_aidd_builtin_tools.py`

**Step 1: Write the failing test**

```python
def test_builtin_protein_preparation_emits_standard_result_v2(tmp_path, monkeypatch):
    protein = tmp_path / "protein.pdb"
    protein.write_text("ATOM      1  N   ALA A   1       0.000   0.000   0.000\nEND\n")
    files = {
        "protein_structure@1": BuiltinToolFile(
            file_id="file-protein",
            filename="protein.pdb",
            path=protein,
            content_type="chemical/x-pdb",
        )
    }
    result = _run_protein_preparation_tool(files, params={"ph": 7.4})
    assert result.standard_result["result_version"] == "aidd.sciminer/result"
    prepared = result.standard_result["artifacts"]["prepared_protein"]
    assert prepared["type"] == "protein_structure@1"
    assert "prepared_pdb" in prepared["files"]
    assert "preparation_report_json" in prepared["files"]
```

**Step 2: Run test to verify it fails**

Run:

```bash
pytest test/test_aidd_builtin_tools.py -k "protein_preparation" -q
```

Expected: FAIL because the handler does not exist.

**Step 3: Write minimal implementation**

- Update `run_builtin_tool` to pass params to handlers. If broad signature changes are risky, add a `run_builtin_tool_with_params` wrapper and make `BuiltinExecutor` call it.
- Handler calls `prepare_protein(...)` with `ProteinPreparationOptions.model_validate(params.get("options") or params)`.
- Write `preparation_report_json` artifact content.
- Build `StandardExecutionResult` with `prepared_protein` output and role files.
- Include relation in result.v2 when possible:

```json
{"from": "protein", "to": "prepared_protein", "type": "derived_from"}
```

Only include relation if standard persistence supports input refs for builtin tasks; otherwise store `source_artifact_version_id` in metadata and leave lineage to Task 8 sync.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest test/test_aidd_builtin_tools.py -k "protein_preparation" -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/agents/aidd/builtin_tools.py backend/app/protein_preparation/engine.py test/test_aidd_builtin_tools.py
git commit -m "feat: run protein preparation builtin"
```

---

### Task 7: Pass Builtin Inputs From Workflow Scheduler

**Files:**
- Modify: `backend/app/services/workflow_scheduler.py`
- Modify: `test/test_workflow_persistence_api.py` or `test/test_workflow_scheduler.py`

**Step 1: Write the failing test**

Create a workflow with `builtin-protein-preparation` consuming `workflow_input:protein_structure@1`. Use the existing fake scheduling helper and assert task params include semantic builtin inputs:

```python
assert scheduled_task.inputs.params["builtin_inputs"] == {
    "protein_structure@1": protein_file.id
}
```

**Step 2: Run test to verify it fails**

Run:

```bash
pytest test/test_workflow_persistence_api.py -k "builtin_inputs" -q
```

Expected: FAIL because `schedule_workflow_node` passes `file_ids` but not `builtin_inputs`.

**Step 3: Write minimal implementation**

In `schedule_workflow_node`, after resolving `input_file_ids` and loading the tool, if tool config is builtin, populate `node_params["builtin_inputs"]` from node semantic/artifact inputs:

```python
if tool.current_version and tool.current_version.config.get("type") == "builtin":
    node_params["builtin_inputs"] = resolve_builtin_input_file_map(
        node=node,
        run=run,
        node_states=node_states,
    )
```

Keep the helper local to `workflow_scheduler.py` and reuse existing source resolution rules. For artifact slot inputs, map the standard type (`protein_structure@1`) to the resolved file id.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest test/test_workflow_persistence_api.py test/test_workflow_validation_standard_artifacts.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/workflow_scheduler.py test/test_workflow_persistence_api.py
git commit -m "fix: pass builtin inputs from workflows"
```

---

### Task 8: Add Board Protein Preparation API

**Files:**
- Create: `backend/app/api/v1/protein_preparation.py`
- Modify: `backend/app/api/v1/__init__.py`
- Modify: `backend/app/schemas/research_boards.py`
- Create: `test/test_protein_preparation_board_api.py`

**Step 1: Write the failing test**

Test start endpoint creates visible board process node, edge, and schedules a task:

```python
async def test_start_protein_preparation_creates_board_node_and_task(...):
    response = await start_protein_preparation(
        board_id,
        ProteinPreparationRequest(
            artifact_id=artifact.id,
            source_node_id="artifact-protein",
            options=ProteinPreparationOptions(ph=7.4),
        ),
        owner,
        db_session,
    )
    data = response["data"]
    assert data["task_id"]
    assert data["preparation_node"]["type"] == "tool"
    assert data["preparation_node"]["tool_id"] == builtin_tool.id
    assert data["edge"]["source"] == "artifact-protein"
    assert data["edge"]["target"] == data["preparation_node"]["id"]
```

Test sync endpoint adds prepared Artifact node after task output contains `standard_artifacts.artifact_ids_by_ref.prepared_protein`.

**Step 2: Run test to verify it fails**

Run:

```bash
pytest test/test_protein_preparation_board_api.py -q
```

Expected: FAIL because route and schema fields do not exist.

**Step 3: Write minimal implementation**

- Extend `BoardNode.type` only if needed. Prefer `type="tool"` for the preparation node to preserve existing canvas behavior.
- Add optional node fields with constrained values:
  - `task_id: str | None`
  - `status: Literal["pending", "running", "success", "failure"] | None`
  - `output_artifact_id: str | None`
- Endpoint: `POST /research-boards/{board_id}/protein-preparations`.
- Use `_load_board` and write access rules from `research_boards.py`; extract shared helpers if duplication becomes meaningful.
- Validate source Artifact belongs to board project and has primary file/version.
- Ensure builtin tool with `settings.AIDD_SYSTEM_USER_ID`; fail clearly if missing.
- Schedule task through `create_and_schedule_tool_task` with:

```python
TaskCreate(
    name=f"Prepare protein {artifact.name}",
    project_id=board.project_id,
    tool_id=builtin_tool.id,
    tool_version_id=builtin_tool.current_version_id,
    params={
        "options": data.options.model_dump(),
        "advanced_options": data.advanced_options,
        "preparation_profile": data.preparation_profile,
        "builtin_inputs": {"protein_structure@1": primary_file_id},
    },
    file_ids=[primary_file_id],
    input_bindings={"protein": artifact_version_id},
)
```

- Insert tool node and edge into board content and increment version.
- Endpoint: `POST /research-boards/{board_id}/protein-preparations/{task_id}/sync` reads successful TaskOutput standard Artifact summary and appends a prepared Artifact node connected from the preparation node.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest test/test_protein_preparation_board_api.py test/test_research_boards_api.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/api/v1/protein_preparation.py backend/app/api/v1/__init__.py backend/app/schemas/research_boards.py test/test_protein_preparation_board_api.py
git commit -m "feat: add board protein preparation api"
```

---

### Task 9: Respect Explicit Board Edges In Workflow Drafts

**Files:**
- Modify: `backend/app/api/v1/research_boards.py`
- Modify: `test/test_research_boards_api.py`

**Step 1: Write the failing test**

Build board content:

```text
artifact-raw -> tool-prep -> tool-docking
```

Assert draft has:

```python
prep_node["artifact_inputs"] == {"protein": "workflow_input:protein_structure@1"}
docking_node["artifact_inputs"] == {"protein": "node:tool-prep:prepared_protein"}
definition["edges"] includes raw->prep and prep->docking with target_input "protein"
```

Also assert if no explicit edge exists, current fallback behavior still binds the first compatible board Artifact input.

**Step 2: Run test to verify it fails**

Run:

```bash
pytest test/test_research_boards_api.py -k "explicit_board_edges" -q
```

Expected: FAIL because workflow draft currently auto-binds by artifact type and does not convert tool-to-tool board edges.

**Step 3: Write minimal implementation**

- Build `content_edges = normalize_board_content(board.content)["edges"]`.
- Index board nodes by id.
- For each tool input slot, prefer incoming explicit board edge sources:
  - source Artifact node with matching standard type -> `workflow_input:<type>`.
  - source Tool node whose output slot type matches target slot type -> `node:<source_tool_id>:<source_output_name>`.
- Only use current first-compatible Artifact fallback when no explicit edge supplies that slot.
- Keep deterministic edge IDs.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest test/test_research_boards_api.py test/test_project_research_boards_api.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/api/v1/research_boards.py test/test_research_boards_api.py
git commit -m "feat: map board process edges to workflows"
```

---

### Task 10: Add Frontend API Wrapper And Board UI Action

**Files:**
- Create: `frontend/src/api/protein-preparation.ts`
- Create: `frontend/src/components/research-boards/ProteinPreparationPanel.vue`
- Create: `frontend/src/components/research-boards/BoardArtifactNodeContent.vue`
- Modify: `frontend/src/views/research-boards/Board.vue`
- Modify: `frontend/src/views/research-boards/Board.spec.ts`

**Step 1: Write the failing test**

In `Board.spec.ts`, mock `startProteinPreparation` and assert:

```ts
expect(wrapper.find('[data-testid="prepare-protein-action"]').exists()).toBe(true)
await wrapper.get('[data-testid="prepare-protein-action"]').trigger('click')
await wrapper.get('[data-testid="protein-preparation-submit"]').trigger('submit')
expect(startProteinPreparation).toHaveBeenCalledWith('board-1', expect.objectContaining({
  artifact_id: 'artifact-1',
  preparation_profile: 'docking_v1',
  options: expect.objectContaining({ ph: 7.4, remove_water: true }),
}))
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npm run test -- Board.spec.ts
```

Expected: FAIL because the UI/API do not exist.

**Step 3: Write minimal implementation**

- `protein-preparation.ts` exports:
  - `startProteinPreparation(boardId, payload)` -> POST `/research-boards/${boardId}/protein-preparations`.
  - `syncProteinPreparation(boardId, taskId)` -> POST `/research-boards/${boardId}/protein-preparations/${taskId}/sync`.
- `BoardArtifactNodeContent.vue` wraps `ArtifactRenderer` and shows action only for `standard_type === 'protein_structure'` or `semantic_type === 'protein_structure@1'`.
- `ProteinPreparationPanel.vue` exposes basic options only:
  - pH number input default 7.4.
  - remove water checkbox.
  - keep metals checkbox.
  - keep cofactors checkbox.
  - remove non-target ligands checkbox.
  - prepared PDB and receptor PDBQT output toggles.
- Board `@prepare-protein` handler posts request, then reloads board/artifacts.

**Step 4: Run test to verify it passes**

Run:

```bash
cd frontend && npm run test -- Board.spec.ts
```

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/api/protein-preparation.ts frontend/src/components/research-boards/ProteinPreparationPanel.vue frontend/src/components/research-boards/BoardArtifactNodeContent.vue frontend/src/views/research-boards/Board.vue frontend/src/views/research-boards/Board.spec.ts
git commit -m "feat(frontend): add protein preparation board action"
```

---

### Task 11: Prefer Prepared Roles In Artifact Rendering And Input Selection

**Files:**
- Modify: `frontend/src/components/artifacts/ProteinStructureArtifact.vue`
- Modify: `frontend/src/components/artifacts/StructureArtifactPreview.vue`
- Modify: `frontend/src/components/artifacts/ArtifactRenderer.spec.ts`
- Modify: `frontend/src/workflow/preflight.ts`
- Optional backend modify: `backend/app/execution/request_builder.py`
- Optional test: `test/test_standard_request_builder.py`

**Step 1: Write the failing test**

Frontend renderer test:

```ts
it('prefers prepared PDB role for protein structures', () => {
  const wrapper = mount(ArtifactRenderer, { props: { artifact: proteinWithPreparedPdbAndRaw } })
  expect(fetchOrPreviewUrl).toContain('/files/prepared_pdb/download')
})
```

Backend request builder test if role selection is needed now:

```python
assert request.inputs["protein"].files["receptor_pdbqt"].path.endswith("receptor.pdbqt")
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npm run test -- ArtifactRenderer.spec.ts
pytest test/test_standard_request_builder.py -k "prepared" -q
```

Expected: FAIL until role preferences are added.

**Step 3: Write minimal implementation**

- Protein renderer preference order: `prepared_pdb`, `structure_file`, `raw_structure_file`.
- Download list should expose `receptor_pdbqt` and `preparation_report_json` roles.
- Workflow preflight accepts `.pdbqt` for `protein_structure@1` only when a tool explicitly needs docking receptor role; avoid broadly making `.pdbqt` the default protein visual format.
- If backend request builder already passes all role files, no backend change is needed. If it chooses one primary path, add a role-preference helper:

```python
ROLE_PREFERENCES = {
    ("protein_structure@1", "builtin-vina-docking"): ["receptor_pdbqt", "prepared_pdb", "structure_file"],
    ("protein_structure@1", "default"): ["prepared_pdb", "structure_file"],
}
```

**Step 4: Run test to verify it passes**

Run:

```bash
cd frontend && npm run test -- ArtifactRenderer.spec.ts
pytest test/test_standard_request_builder.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/components/artifacts/ProteinStructureArtifact.vue frontend/src/components/artifacts/StructureArtifactPreview.vue frontend/src/components/artifacts/ArtifactRenderer.spec.ts frontend/src/workflow/preflight.ts backend/app/execution/request_builder.py test/test_standard_request_builder.py
git commit -m "feat: prefer prepared protein roles"
```

---

### Task 12: End-To-End Workflow Regression

**Files:**
- Create or modify: `test/test_protein_preparation_workflow_api.py`
- Modify: `frontend/src/composables/useWorkflowPersistence.spec.ts`
- Modify: `frontend/src/views/workflow/free-workflow.spec.ts` if saved workflow payload changes.

**Step 1: Write the failing test**

Backend e2e test should cover:

1. Raw protein Artifact node on board.
2. Protein preparation tool node connected from raw Artifact.
3. Downstream docking/pocket tool connected from preparation node.
4. `create_workflow_draft` produces a runnable definition with standard artifact node references.
5. Creating a workflow run schedules preparation first.
6. Syncing after preparation success schedules downstream node with prepared protein artifact file id.

**Step 2: Run test to verify it fails**

Run:

```bash
pytest test/test_protein_preparation_workflow_api.py -q
```

Expected: FAIL until preceding tasks are fully integrated.

**Step 3: Write minimal implementation**

Patch integration gaps only. Do not add new abstractions unless the failing e2e test proves they are needed.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest test/test_protein_preparation_workflow_api.py test/test_workflow_persistence_api.py test/test_research_boards_api.py -q
cd frontend && npm run test -- useWorkflowPersistence.spec.ts free-workflow.spec.ts
```

Expected: PASS.

**Step 5: Commit**

```bash
git add test/test_protein_preparation_workflow_api.py frontend/src/composables/useWorkflowPersistence.spec.ts frontend/src/views/workflow/free-workflow.spec.ts
git commit -m "test: cover protein preparation workflow path"
```

---

### Task 13: Final Verification

**Files:**
- No production file edits unless verification exposes a defect.

**Step 1: Run targeted backend suite**

```bash
pytest \
  test/test_artifact_standard_registry.py \
  test/test_protein_preparation_schemas.py \
  test/test_protein_preparation_engine.py \
  test/test_aidd_builtin_tools.py \
  test/test_aidd_builtin_task_tools.py \
  test/test_aidd_builtin_standard_artifacts.py \
  test/test_protein_preparation_board_api.py \
  test/test_research_boards_api.py \
  test/test_workflow_persistence_api.py \
  test/test_protein_preparation_workflow_api.py
```

Expected: PASS.

**Step 2: Run frontend targeted suite**

```bash
cd frontend && npm run test -- Board.spec.ts ArtifactRenderer.spec.ts useWorkflowPersistence.spec.ts free-workflow.spec.ts
```

Expected: PASS.

**Step 3: Run full verification**

```bash
pytest test
cd frontend && npm run test
cd frontend && npm run build
git diff --check
```

If `pytest test` exceeds the shell timeout, split by file groups and record all groups and counts. Do not claim full pass from a timed-out command.

**Step 4: Final commit if needed**

Only commit verification fixes if files changed:

```bash
git status --short
git add <only related files>
git commit -m "fix: harden protein preparation workflow"
```

Expected: no unrelated dirty files staged.
