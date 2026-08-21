# Workflow Artifact Binding Boundary Design

## Context

Workflow edges currently bind outputs to inputs mainly by broad semantic type, such as `protein_structure@1` or `ligand_structure@1`. That is not enough for drug discovery workflows. A raw PDB fetched from RCSB can contain waters, ligands, or other heterogens and still be a valid `protein_structure@1`. Downstream tools may need a prepared PDB, a receptor PDBQT, or a ligand 3D SDF. The platform already has standard Artifact roles and protein preparation outputs, but workflow binding does not yet use those roles as the authority.

## Decision

Put the authoritative seam in a backend module named `ArtifactBindingResolver`. The module decides whether an upstream standard ArtifactVersion can satisfy a target tool input slot, which file role should be used, and whether the user must run a preparation or conversion step first.

Frontend code may mirror this decision for faster feedback, but the backend is the only authority used for node standalone runs and full workflow scheduling.

## Non-Decisions

- Do not silently insert hidden workflow nodes.
- Do not make model-side cleanup the primary contract.
- Do not split `protein_structure@1` into many raw/prepared semantic types in v1.
- Do not rely only on filename extensions to infer readiness.
- Do not let each executor pick its own role-selection behavior.

## Module Boundary

### Module

`ArtifactBindingResolver`

### Interface

The external interface should stay small and return a decision object:

```python
resolve_binding(
    *,
    target_tool_config: dict,
    input_slot: dict,
    candidate_artifact_version_id: str,
) -> ArtifactBindingDecision
```

The decision object should contain:

```python
{
  "status": "ready" | "needs_preparation" | "needs_conversion" | "invalid",
  "input_name": "protein",
  "standard_type": "protein_structure@1",
  "selected_role": "prepared_pdb",
  "selected_file_id": "...",
  "artifact_version_id": "...",
  "reason": "Prepared protein PDB selected for pocket prediction.",
  "suggested_tool_slug": "builtin-protein-preparation"
}
```

### Implementation Responsibilities

- Load ArtifactVersion, ArtifactVersionFile, and File records.
- Validate standard type compatibility.
- Read available file roles and Artifact metadata.
- Apply tool input requirements such as required roles, preferred roles, and readiness policy.
- Return a deterministic decision with a user-facing reason.
- Provide a legacy projection for old executors, for example turning `prepared_pdb` into `input_files.protein_pdb` for an `ssh_job` tool.

### Callers

- Full workflow scheduling uses the resolver before creating a task.
- Standalone node runs use the resolver before creating a task.
- Workflow preflight displays resolver decisions.
- Frontend canvas may use a lightweight mirror, but must not be the authority.

## Tool Input Requirements

Tool inputs need one more layer beyond `type`:

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

Recommended v1 policies:

- `allow_raw`: raw `structure_file` is acceptable.
- `prefer_prepared_warn_raw`: use `prepared_pdb` when present; allow raw with a warning and an obvious preparation suggestion.
- `require_prepared`: block raw inputs and suggest preparation.
- `require_receptor`: require `receptor_pdbqt`, usually for Vina/Smina-style docking.
- `prefer_3d_ligand`: use `structure_3d_sdf`; if only 2D exists, suggest conformer generation or ligand preparation.

## Protein Rules

- `builtin-fetch-pdb` output is raw unless metadata says otherwise.
- `builtin-protein-preparation` output is prepared and should include `prepared_pdb`; optionally `receptor_pdbqt`.
- LVpocket should prefer `prepared_pdb`. If only raw `structure_file` exists, v1 should warn and recommend protein preparation. If the tool owner marks it as `require_prepared`, block the run.
- Docking tools should require or strongly prefer `receptor_pdbqt`.

## Ligand Rules

- PubChem ligand output may include `structure_file`, `structure_2d_sdf`, and `structure_3d_sdf`.
- Docking should prefer prepared 3D ligand roles.
- If only 2D exists, return `needs_conversion` or `needs_preparation` with a suggested conformer or ligand preparation tool.

## Legacy Executor Projection

The resolver should not force every executor to understand ArtifactVersion roles immediately. It can project decisions into old task payloads:

- `ssh_job` root file field `protein_pdb` receives the selected file role path.
- legacy `file_ids` contains only selected files, not every file in the Artifact.
- Tool Package v2 and remote-tool.v1 continue to receive the full role map via `input_bindings` / standard Artifact inputs.

## Error Handling

- `invalid`: standard type mismatch, missing ArtifactVersion, missing required file role, inaccessible file, or unknown policy.
- `needs_preparation`: valid raw input, but downstream requires prepared protein.
- `needs_conversion`: valid input, but downstream requires another format or 3D state.
- `ready`: selected role and file are final and executor-safe.

## Testing Strategy

- Resolver unit tests cover raw protein, prepared protein, receptor PDBQT, 2D ligand, 3D ligand, and missing role cases.
- Workflow scheduler tests prove raw protein does not schedule a `require_prepared` node.
- Standalone node run tests prove old `ssh_job` payloads receive the selected role file instead of the newest same-semantic file.
- Frontend preflight tests prove users see a clear action: prepare protein, convert ligand, or run now.

## Rollout

1. Add input role requirement fields to tool contracts and response schemas.
2. Implement backend `ArtifactBindingResolver` with tests.
3. Wire full workflow scheduling to resolver decisions.
4. Wire standalone node runs to resolver decisions.
5. Add frontend preflight and node-panel display for `needs_preparation` and `needs_conversion`.
6. Update builtin and drug-discovery template contracts for protein and ligand readiness.
