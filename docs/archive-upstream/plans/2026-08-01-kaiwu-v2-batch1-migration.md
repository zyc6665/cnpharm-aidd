# Kaiwu v2 Batch 1 Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate the first Kaiwu model batch to Tool Package v2 without breaking the existing ssh_job tools.

**Architecture:** Put adapters in model-side runtime packages, not in platform Tool Packages.
Tool Package v2 only declares standard Artifact contracts and points to a thin runner that delegates to
the model runtime entrypoint. Deploy remote code only under a new v2 directory, leaving existing
`/workspace/*/platform_run.sh` files unchanged.

**Tech Stack:** Python 3 adapters, Bash entrypoints, Tool Package v2 manifests, pytest, SSH + docker exec for remote deployment.

---

### Task 1: LVpocket model-side runtime

**Files:**
- Create: `model/LVpocket/MODEL_PACKAGE.yaml`
- Create: `model/LVpocket/platform_run.sh`
- Create: `model/LVpocket/src/lvpocket_runtime/**`
- Create: `model/LVpocket/tests/test_lvpocket_runtime_contract.py`
- Modify: `example/LVpocket/tool-package-v2/runner/platform_run_v2.sh`
- Modify: `test/test_lvpocket_tool_package_v2.py`

**Step 1: Write the failing test**

Add a model-side test that builds a legacy LVpocket output directory with `pocket0.pdb`,
`protein_pocket_residues.pdb`, `prediction.json`, and verifies `lvpocket_runtime` emits
`binding_pocket@1` with `residue_pocket_pdb`, `atom_pocket_pdb`, and
`pocket_metadata_json`.

**Step 2: Run the test to verify it fails**

Run:

```bash
pytest test/test_lvpocket_tool_package_v2.py -q
```

Expected: failure because `model/LVpocket/src/lvpocket_runtime` does not exist.

**Step 3: Implement the minimal adapter**

Implement `lvpocket_runtime.result_builder.write_standard_result(...)` and a
`platform_run.sh` that calls `lvpocket_runtime.cli`. The Tool Package runner stays a
thin delegate and contains no model-private adapter code.

**Step 4: Verify**

Run:

```bash
pytest test/test_lvpocket_tool_package_v2.py model/LVpocket/tests/test_lvpocket_runtime_contract.py -q
python -m app.tool_packages.validator example/LVpocket/tool-package-v2
```

### Task 2: MolP-PC v2 alignment

**Files:**
- Modify: `example/MolP-PC/tool-package-v2/tool.yaml`
- Modify: `model/MolP-PC/MODEL_PACKAGE.yaml`
- Modify: `model/MolP-PC/src/molp_pc_runtime/result_builder.py`
- Rename: `model/MolP-PC/tests/test_runtime_contract.py` to `model/MolP-PC/tests/test_molp_pc_runtime_contract.py`
- Modify: `test/test_molp_pc_tool_package_v2.py`

**Step 1: Write the failing test**

Assert the manifest version matches current DB version `0.1.1` and the runtime
artifact URIs include `0.1.1`.

**Step 2: Run the test to verify it fails**

Run:

```bash
pytest test/test_molp_pc_tool_package_v2.py -q
```

Expected: failure because the example still declares `0.1.0`.

**Step 3: Update manifest and examples**

Change Tool Package and Model Package metadata/runtime URIs to `0.1.1`. Keep placeholder
digests until real runtime artifacts are built. Keep adapter logic in `molp_pc_runtime`.

**Step 4: Verify**

Run:

```bash
pytest test/test_molp_pc_tool_package_v2.py model/MolP-PC/tests/test_molp_pc_runtime_contract.py -q
python -m app.tool_packages.validator example/MolP-PC/tool-package-v2
```

### Task 3: MSIGN v2 package

**Files:**
- Create: `model/MSIGN/MODEL_PACKAGE.yaml`
- Create: `model/MSIGN/platform_run.sh`
- Create: `model/MSIGN/src/msign_runtime/**`
- Create: `model/MSIGN/tests/test_msign_runtime_contract.py`
- Create: `example/MSIGN/tool-package-v2/tool.yaml`
- Create: `example/MSIGN/tool-package-v2/runner/entrypoint.sh`
- Create: `example/MSIGN/tool-package-v2/runner/platform_run_v2.sh`
- Create: `example/MSIGN/tool-package-v2/schemas/parameters.schema.json`
- Create: `example/MSIGN/tool-package-v2/schemas/result.v2.example.json`
- Create: `example/MSIGN/tool-package-v2/examples/request.json`
- Create: `example/MSIGN/tool-package-v2/examples/output/**`
- Create: `test/test_msign_tool_package_v2.py`

**Step 1: Write the failing tests**

Assert MSIGN declares `protein_structure@1 + ligand_structure@1` inputs and
`molecule_table@1 + run_report@1` outputs. Assert `msign_runtime` converts a legacy
`prediction.json` into a standard affinity CSV and report.

**Step 2: Run the tests to verify they fail**

Run:

```bash
pytest test/test_msign_tool_package_v2.py -q
```

Expected: failure because the v2 package does not exist.

**Step 3: Implement the package**

Create a model-side runtime package and a Tool Package v2 package matching existing
manifest/runtime policy. Implement `msign_runtime.result_builder` to convert old MSIGN
`outputs.prediction` fields into a
`molecule_table@1` CSV with `complex_id`, `predicted_affinity`,
`predicted_ligand_to_pocket`, `predicted_pocket_to_ligand`, `scale`,
`model_name`, `distance_angstrom`, and `device`.

**Step 4: Verify**

Run:

```bash
pytest test/test_msign_tool_package_v2.py model/MSIGN/tests/test_msign_runtime_contract.py -q
python -m app.tool_packages.validator example/MSIGN/tool-package-v2
```

### Task 4: Remote non-destructive deployment

**Files:**
- Remote create only: `/workspace/sciminer-v2-tools/lvpocket-standard-pocket`
- Remote create only: `/workspace/sciminer-v2-tools/molp-pc-property-prediction`
- Remote create only: `/workspace/sciminer-v2-tools/msign-affinity-prediction`

**Step 1: Inspect remote destination**

Confirm whether `/workspace/sciminer-v2-tools` exists. Do not overwrite old
model directories.

**Step 2: Upload package runtime files**

Upload Tool Package metadata and the matching `model/` runtime wrapper. Do not upload secrets,
weights, conda envs, or generated caches.

**Step 3: Verify remote files**

Run read-only checks after upload:

```bash
docker exec kaiwu bash -lc 'find /workspace/sciminer-v2-tools -maxdepth 3 -type f | sort'
```

### Task 5: Review and commit

**Files:**
- All local files touched by Tasks 1-3 and this plan.

**Step 1: Run verification**

Run focused tests and validators for LVpocket, MolP-PC, and MSIGN.

**Step 2: Review**

Check `git diff --check`, scan for secrets, and inspect staged diff.

**Step 3: Commit**

Commit with:

```bash
git commit -m "feat(tool-packages): migrate kaiwu batch1 v2 packages"
```

### Platform smoke verification

Run the full platform flow after local tests and remote upload:

1. Start FastAPI locally with `TASK_EXECUTION_BACKEND=direct`.
2. Create temporary non-current `ToolVersion` rows for the three existing Kaiwu tools.
3. Upload real input files through `/api/v1/files/upload`.
4. Create tasks through `/api/v1/tasks`.
5. Poll `/api/v1/tasks/{task_id}` until completion and verify `result_version == "aidd.sciminer/result.v2"`.

Verified on 2026-08-01 against remote Kaiwu container path `/workspace/sciminer-v2-tools`:

| Existing platform tool | Temporary smoke version | Task ID | Status | Result artifacts |
| --- | --- | --- | --- | --- |
| `lvpocket-pocket-prediction` | `0.1.2-v2-smoke-20260801111226` | `146a5106-4687-4a95-996e-72d98d8434fd` | `success` | `pocket`, `report` |
| `molp-pc-property-prediction` | `0.1.1-v2-smoke-20260801111226` | `a8c7f1fd-e13d-4f9f-9e77-0cea2b7b6182` | `success` | `properties`, `report` |
| `msign-affinity-prediction` | `0.1.1-v2-smoke-20260801111226` | `e443d2d0-dfc0-4ecd-8bf2-78b54162bb04` | `success` | `affinity`, `report` |

Notes:
- The remote deployment is non-destructive: old `/workspace/*/platform_run.sh` files remain unchanged.
- The first LVpocket smoke task exposed a real legacy-layout mismatch: LVpocket produced `artifacts/lv_results/input/pocket0.pdb`; `lvpocket_runtime` now reads paths declared in legacy `result.json` before fallback filenames.
- The smoke versions do not set `tool_package_manifest` in DB config yet because direct `/api/v1/tasks` does not attach `project_id`; standard Artifact persistence currently requires `task.extra_data.project_id`. This is the next platform-side gap before enabling ArtifactVersion persistence for ad-hoc task-center runs.
