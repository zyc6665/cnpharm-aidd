# Pocket2Mol K8s Runtime Verification Implementation Plan

> **For Codex:** Execute the steps in order. Preserve SSH version `0.1.2`; do not enable global K8s execution or modify persistent environment settings.

**Goal:** Verify the registered Pocket2Mol image and close the K8s request, input, model, and result contract before creating a fresh isolated run.

**Architecture:** First compare the platform's registered immutable image reference with the private Registry and local build context. Then validate the model adapter's request materialization, staged standard ArtifactVersion inputs, model entrypoint, and result upload contract. Only after these checks pass, run an isolated K8s smoke task without changing the SSH default or global executor configuration.

**Tech Stack:** FastAPI, SQLite/SQLAlchemy, Docker Registry v2, Kubernetes Jobs, pytest, Pocket2Mol runtime adapter.

---

### Task 1: Verify registered image identity

**Files:** None; read-only platform database and Registry queries.

**Steps:**
1. Read Pocket2Mol `ImageAsset` rows and matching `ToolVersion` runtime references without changing their state.
2. Query the Registry manifest for the registered tag and compare its digest with the database reference.
3. Compare local archive metadata with registered import metadata. Do not retry full-archive hashing if the filesystem blocks reads.
4. Record the K8s ToolVersion activation state and stop before any state change if it is inactive.

**Acceptance:** The database and Registry manifest digests agree; the exact active/inactive state and archive comparison limits are recorded.

### Task 2: Verify adapter and request contract

**Files:**
- Review: `model-build/pocket2mol-pocket-ligand-generation-v4/platform_adaptor/entrypoint.sh`
- Review: `model-build/pocket2mol-pocket-ligand-generation-v4/platform_adaptor/platform_run_v2.sh`
- Review: `model-build/pocket2mol-pocket-ligand-generation-v4/platform_adaptor/object_storage.py`
- Test: `model-build/pocket2mol-pocket-ligand-generation-v4/model/tests/test_pocket2mol_runtime_contract.py`

**Steps:**
1. Run the existing request-materialization contract test.
2. Run the Pocket2Mol runtime contract suite.
3. Confirm the standard request is materialized at the exact `--params-json` path before model invocation.
4. Confirm standard `binding_pocket@1` roles map to the legacy Pocket2Mol input and output uses `result.v2`.
5. Change adapter code only if a contract test demonstrates a real defect; add a failing test before changing implementation.

**Acceptance:** Request file, staged inputs, model input mapping, and result manifest contracts pass locally.

### Task 3: Run image-level and isolated K8s smoke checks

**Files:** No persistent platform configuration changes. Any temporary Kubernetes resources must be uniquely named and removed after verification.

**Steps:**
1. Confirm the registered K8s ToolVersion is eligible for an isolated run. Do not activate it through direct database writes.
2. Inspect image startup behavior using the registered digest; use a bounded smoke command that does not run full sampling where possible.
3. If activation or credentials are required, stop and report the precise administrator action needed.
4. After startup and input staging pass, create a fresh one-sample K8s task; do not retry the historical failed task.
5. Verify Pod logs, uploaded `result.json`, task status, and cleanup of only resources created for this smoke run.

**Acceptance:** A fresh isolated K8s task succeeds with the registered immutable digest, and no SSH/global executor settings are changed.
