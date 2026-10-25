# Protein Preparation Workflow Design

## Context

The platform can now import external protein structures, such as RCSB PDB records,
as standard `protein_structure@1` Artifacts and place them on the research board.
Raw downloaded proteins are not always ready for downstream workflows. Docking,
affinity prediction, and some pocket or molecular modeling tools usually need a
prepared receptor: waters removed when appropriate, hydrogens added, protonation
state controlled, and tool-specific formats such as PDBQT generated.

The first version should make protein preparation a visible, auditable step in the
research workflow. It must not silently overwrite the raw imported structure.

## Goals

- Add a manual one-click protein preparation action for `protein_structure@1`.
- Represent preparation as a first-class node on the research board and workflow canvas.
- Preserve the raw imported protein Artifact and create a derived prepared Artifact.
- Produce downstream-ready roles such as prepared PDB and receptor PDBQT.
- Store preparation parameters and logs for reproducibility.
- Keep the first UI simple while reserving an advanced-options interface for later.

## Non-Goals

- Do not automatically prepare every external protein import in v1.
- Do not expose every protonation, chain, metal, or residue-repair option in v1 UI.
- Do not replace existing tool contracts or force all downstream tools to change at once.
- Do not hide preparation as a backend-only side effect.

## Chosen Approach

Use a platform-managed Protein Preparation workflow node. From the user's point of
view, the board flow is:

```text
Raw Protein Artifact -> Protein Preparation Node -> Prepared Protein Artifact -> Downstream Tool Nodes
```

The preparation action can be launched from an Artifact card or board action, but
launching it creates visible canvas state: a preparation node connected to the raw
protein Artifact and, after successful execution, a prepared protein Artifact node.

This approach gives traceability without forcing users to manually register a
generic tool before they can prepare a receptor.

## Standard Artifact Model

Keep `protein_structure@1` as the logical type and extend its file roles rather
than introducing `protein_structure@2` immediately. The current required primary
`structure_file` remains compatible with existing imports and tools.

Add optional roles:

- `raw_structure_file`: original unmodified PDB/CIF if a prepared Artifact needs to keep a copy.
- `prepared_pdb`: cleaned and prepared PDB structure.
- `prepared_pqr`: optional PQR output when a PDB2PQR-style pipeline is available.
- `receptor_pdbqt`: receptor file for AutoDock/Vina-style downstream tools.
- `preparation_report_json`: structured report with parameters, warnings, tool versions, and file role map.

Add metadata fields:

- `preparation_status`: `raw`, `prepared`, or `failed`.
- `preparation_profile`: first value `docking_v1`.
- `ph`: numeric pH used for hydrogen/protonation handling.
- `remove_water`, `keep_metals`, `keep_cofactors`, `remove_non_target_ligands`: booleans.
- `preparation_engine`: implementation name, for example `pdbfixer_openbabel_v1`.
- `source_artifact_version_id`: raw ArtifactVersion used as input.

## Preparation Interface

Expose one versioned backend interface for starting preparation. The request shape
should support basic v1 settings and future advanced mode:

```json
{
  "artifact_id": "raw-artifact-id",
  "artifact_version_id": "optional-version-id",
  "board_id": "optional-board-id",
  "source_node_id": "optional-board-node-id",
  "position": { "x": 360, "y": 120 },
  "preparation_profile": "docking_v1",
  "options": {
    "ph": 7.4,
    "remove_water": true,
    "keep_metals": true,
    "keep_cofactors": true,
    "remove_non_target_ligands": true,
    "output_formats": ["prepared_pdb", "receptor_pdbqt"]
  },
  "advanced_options": {}
}
```

`advanced_options` is intentionally opaque in v1 but must be persisted in the
report. Later versions can validate known advanced fields without changing the
endpoint shape.

## Processing Pipeline

The preparation implementation should live behind a small module interface, for
example:

```python
prepare_protein(input_file, options) -> ProteinPreparationResult
```

The caller should not know whether the implementation uses PDBFixer, PDB2PQR,
Meeko, Open Babel, or a containerized adapter. The module returns output files,
metadata, warnings, and errors. This keeps preparation logic local and testable.

Recommended v1 engine order:

1. Parse and validate the input structure.
2. Remove water if requested.
3. Preserve or remove heterogens according to metal/cofactor/ligand policy.
4. Repair common missing atoms/residues where the selected engine supports it.
5. Add hydrogens using requested pH.
6. Write `prepared_pdb`.
7. Convert/write `receptor_pdbqt`, preferably with a receptor-aware tool; use Open Babel fallback only when acceptable.
8. Write `preparation_report_json`.

Failures should return a clear validation error and never mutate the raw Artifact.

## Board And Workflow Behavior

Research board behavior:

- Raw protein Artifact nodes show a “准备蛋白” action.
- Starting preparation inserts or updates a `protein_preparation` processing node.
- The processing node records status: pending, running, success, failure.
- On success, a prepared Artifact node is added and connected from the processing node.

Workflow behavior:

- `protein_preparation` is exported as a tool-like workflow node.
- Input slot: `protein: protein_structure@1`.
- Output slot: `prepared_protein: protein_structure@1`.
- Downstream tools can connect to the prepared Artifact.
- Workflow run inputs still use standard `protein_structure@1`, while role selection happens in the request-building layer.

## Downstream Role Selection

Existing downstream tools may only declare `protein_structure@1`. To avoid breaking
contracts, request builders should pick the best available role by tool need:

- Vina/receptor docking: prefer `receptor_pdbqt`, fallback to `prepared_pdb`, then `structure_file`.
- Pocket prediction: prefer `prepared_pdb`, fallback to `structure_file`.
- General visualization/download: show all known roles and keep `structure_file` as default if no prepared role exists.

This can be implemented as an internal role-preference map keyed by standard type
and optional tool slug/executor need.

## Frontend Experience

First version UI should expose only:

- pH, default `7.4`.
- Remove water, default on.
- Keep metals, default on.
- Keep cofactors, default on.
- Remove non-target ligands, default on.
- Output formats, default `prepared_pdb` and `receptor_pdbqt`.

Advanced settings are not shown in v1, but the backend accepts and records
`advanced_options` for future upgrades.

Prepared protein Artifact cards should show available roles and download links.
For visualization, `prepared_pdb` should be preferred over raw `structure_file`.

## Error Handling

- Unsupported input format: reject before creating output Artifact.
- Missing external binary or engine: return a user-facing error with remediation.
- Failed conversion to PDBQT: keep `prepared_pdb` only if the request allowed partial output; otherwise fail the task.
- Ambiguous chains or ligands: warn in the report and use default policy in v1.
- Any storage failure: rollback database changes and remove uploaded partial files.

## Testing Strategy

Backend tests:

- Protein preparation request schema accepts basic options and preserves `advanced_options`.
- Preparation module creates expected role files from a small PDB fixture.
- Failure path does not create a prepared Artifact.
- Board action creates preparation node and prepared Artifact node with edges.
- Workflow draft export preserves the preparation node and its artifact slots.

Frontend tests:

- Board shows “准备蛋白” for protein Artifact nodes.
- Submitting basic options calls the preparation API and refreshes board state.
- Prepared Artifact renderer prefers `prepared_pdb` and exposes `receptor_pdbqt` download.
- Workflow mapping preserves preparation node slots and edges.

## Rollout Plan

1. Extend `protein_structure@1` roles and metadata.
2. Add backend preparation schemas and module interface.
3. Implement v1 preparation engine and persistence of derived Artifact lineage.
4. Add board API for creating/running preparation nodes.
5. Add frontend board action and simple options panel.
6. Update workflow draft conversion and role-preference request building.
7. Add regression tests and run backend/frontend verification.
