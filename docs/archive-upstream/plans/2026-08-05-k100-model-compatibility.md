# K100 Model Compatibility Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a repeatable K100 compatibility and binary-delivery process, starting with MolP-PC, without exposing complete model source on the commercial test machine.

**Architecture:** Keep the platform Interface fixed around standard task directories, `platform_run.sh`, `result.json`, logs, and Artifact outputs. Put K100/DTK/Python differences behind model-side Adapter and binary delivery scripts. Use MolP-PC as the first deep Module: a small runtime Interface hiding original model invocation, dependency probing, Cython compilation, and result normalization.

**Tech Stack:** Bash, Python 3.11, Cython or Nuitka, Docker image `2.7.1-ubuntu22.04-dtk26.04-py3.11`, existing MolP-PC package under `model/MolP-PC`, pytest for package contract checks.

---

### Task 1: Probe The Target K100 Container

**Files:**
- Create: `docs/verification/k100-target-probe-template.md`

**Step 1: Record the probe commands**

Create a document containing this command template. Replace `<container>` only on the test machine.

```bash
docker exec -it <container> bash -lc '
set -euo pipefail
cat /etc/os-release
uname -m
python -V
python - <<"PY"
import sys, sysconfig, platform, importlib.util
print("executable =", sys.executable)
print("version =", sys.version)
print("platform =", platform.platform())
print("SOABI =", sysconfig.get_config_var("SOABI"))
print("EXT_SUFFIX =", sysconfig.get_config_var("EXT_SUFFIX"))
for name in ["numpy", "pandas", "scipy", "sklearn", "torch", "dgl", "rdkit", "onnxruntime"]:
    print(name, "FOUND" if importlib.util.find_spec(name) else "missing")
PY
command -v gcc && gcc --version | head -1 || true
ldd --version | head -1
find /usr /opt -maxdepth 3 -iname "*dtk*" -o -iname "*k100*" 2>/dev/null | head -80 || true
'
```

**Step 2: Run the probe on the test machine**

Run the command in the existing `2.7.1-ubuntu22.04-dtk26.04-py3.11` container.

Expected: output includes Python 3.11, `EXT_SUFFIX`, glibc version, CPU architecture, and visible DTK/K100 libraries or packages.

**Step 3: Save the output**

Create one dated report file.

```bash
mkdir -p docs/verification/k100
vi docs/verification/k100/YYYY-MM-DD-target-container-probe.md
```

Expected: report contains the full probe output and container image tag.

**Step 4: Commit**

```bash
git add docs/verification/k100-target-probe-template.md docs/verification/k100/YYYY-MM-DD-target-container-probe.md
git commit -m "docs: add k100 target container probe"
```

### Task 2: Run MolP-PC Legacy Env As Internal Compatibility Probe

**Files:**
- Read: `model/kaiwu-venv-model-bundles/kaiwu-venv-model-bundles-20260805T074701Z/BUNDLE_INDEX.tsv`
- Read: `model/MolP-PC/platform_run.sh`
- Read: `model/MolP-PC/examples/sample_input/smiles.csv`
- Create: `docs/verification/k100/molp-pc-legacy-env-probe.md`

**Step 1: Prepare a non-commercial internal test directory**

Do this only if the test environment policy allows temporary source exposure for internal probing. Do not use this as the final commercial delivery package.

```bash
mkdir -p /tmp/sciminer-k100-probe/molp-pc
tar --use-compress-program=unzstd -xf code.tar.zst -C /tmp/sciminer-k100-probe/molp-pc
tar --use-compress-program=unzstd -xf env.tar.zst -C /tmp/sciminer-k100-probe/molp-pc
```

Expected: extracted code and env exist under `/tmp/sciminer-k100-probe/molp-pc`.

**Step 2: Check whether the packed Python starts**

```bash
/tmp/sciminer-k100-probe/molp-pc/env/bin/python -V
/tmp/sciminer-k100-probe/molp-pc/env/bin/python - <<'PY'
import sys
print(sys.executable)
for name in ["numpy", "pandas", "torch", "dgl"]:
    try:
        __import__(name)
        print(name, "OK")
    except Exception as exc:
        print(name, "FAIL", type(exc).__name__, exc)
PY
```

Expected: Python 3.8 starts. Import failures are recorded, not patched blindly.

**Step 3: Run the existing platform entry if imports pass**

```bash
bash /tmp/sciminer-k100-probe/molp-pc/MolP-PC/platform_run.sh \
  --task-id k100-molp-pc-legacy-probe \
  --input-dir /tmp/sciminer-k100-probe/molp-pc/MolP-PC/examples/sample_input \
  --output-dir /tmp/sciminer-k100-probe/molp-pc/output \
  --params-json /tmp/sciminer-k100-probe/molp-pc/MolP-PC/examples/request.legacy.json \
  --work-dir /tmp/sciminer-k100-probe/molp-pc/work \
  --device cpu
```

Expected: either `output/result.json` is produced or the failure identifies a concrete ABI/dependency/operator issue.

**Step 4: Write the compatibility note**

Record:
- Whether cp38 Python starts.
- Which imports pass or fail.
- Whether `platform_run.sh` writes `result.json`.
- Whether output matches platform Artifact contract.

**Step 5: Commit**

```bash
git add docs/verification/k100/molp-pc-legacy-env-probe.md
git commit -m "docs: record molp-pc legacy env k100 probe"
```

### Task 3: Add MolP-PC Binary Delivery Template

**Files:**
- Create: `model/MolP-PC/binary_delivery/README.md`
- Create: `model/MolP-PC/binary_delivery/pyproject.toml`
- Create: `model/MolP-PC/binary_delivery/setup.py`
- Create: `model/MolP-PC/binary_delivery/runtime_main.py`
- Create: `model/MolP-PC/binary_delivery/platform_run.sh`
- Create: `model/MolP-PC/binary_delivery/scripts/build_binary_bundle.sh`
- Create: `model/MolP-PC/binary_delivery/scripts/check_no_source_leak.sh`
- Test: `model/MolP-PC/tests/test_binary_delivery_layout.py`

**Step 1: Write the failing layout test**

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / "binary_delivery"


def test_binary_delivery_template_files_exist():
    expected = [
        BINARY / "README.md",
        BINARY / "pyproject.toml",
        BINARY / "setup.py",
        BINARY / "runtime_main.py",
        BINARY / "platform_run.sh",
        BINARY / "scripts" / "build_binary_bundle.sh",
        BINARY / "scripts" / "check_no_source_leak.sh",
    ]
    missing = [path for path in expected if not path.exists()]
    assert missing == []
```

**Step 2: Run test to verify it fails**

```bash
pytest model/MolP-PC/tests/test_binary_delivery_layout.py -q
```

Expected: FAIL because `binary_delivery` files do not exist yet.

**Step 3: Create the minimal template**

`runtime_main.py` should be the only readable Python launcher in the final bundle. It delegates to a compiled module.

```python
from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Run compiled MolP-PC runtime")
    parser.add_argument("--model-root", required=True)
    parser.add_argument("--task-id", default="")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--params-json", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--device", default="")
    args = parser.parse_args()

    from molp_pc_compiled import run

    return int(run(vars(args)))


if __name__ == "__main__":
    raise SystemExit(main())
```

`setup.py` should compile selected runtime modules into a py3.11 extension and exclude generated `.c` files from the final package.

**Step 4: Add the source leak checker**

The checker must fail if the output bundle contains protected `.py` files outside the allowlist.

```bash
#!/usr/bin/env bash
set -euo pipefail

BUNDLE_DIR="${1:?bundle dir is required}"
find "${BUNDLE_DIR}" -type f -name '*.py' | while read -r path; do
  case "${path}" in
    */runtime_main.py) ;;
    *) echo "Protected Python source leaked: ${path}" >&2; exit 1 ;;
  esac
done
find "${BUNDLE_DIR}" -type f -name '*.c' -print -quit | grep -q . && {
  echo "Generated C source leaked" >&2
  exit 1
} || true
```

**Step 5: Run tests**

```bash
pytest model/MolP-PC/tests/test_binary_delivery_layout.py model/MolP-PC/tests/test_molp_pc_runtime_contract.py -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add model/MolP-PC/binary_delivery model/MolP-PC/tests/test_binary_delivery_layout.py
git commit -m "feat(model): add molp-pc binary delivery template"
```

### Task 4: Build MolP-PC Binary Bundle In Trusted Builder

**Files:**
- Modify: `model/MolP-PC/binary_delivery/scripts/build_binary_bundle.sh`
- Create: `docs/verification/k100/molp-pc-binary-build.md`

**Step 1: Run builder with the target base image**

```bash
docker run --rm -it \
  -v "$PWD/model/MolP-PC:/workspace/MolP-PC:ro" \
  -v "$PWD/dist:/workspace/dist" \
  2.7.1-ubuntu22.04-dtk26.04-py3.11 \
  bash /workspace/MolP-PC/binary_delivery/scripts/build_binary_bundle.sh
```

Expected: `dist/molp-pc-k100-binary/` contains `platform_run.sh`, `runtime_main.py`, compiled `molp_pc_compiled*.so`, weights, manifest, examples, and `SHA256SUMS`.

**Step 2: Check no protected source leaked**

```bash
bash model/MolP-PC/binary_delivery/scripts/check_no_source_leak.sh dist/molp-pc-k100-binary
```

Expected: PASS with no output.

**Step 3: Check the compiled extension imports**

```bash
docker run --rm -it \
  -v "$PWD/dist/molp-pc-k100-binary:/bundle:ro" \
  2.7.1-ubuntu22.04-dtk26.04-py3.11 \
  bash -lc 'PYTHONPATH=/bundle/lib python -c "import molp_pc_compiled; print(molp_pc_compiled)"'
```

Expected: import succeeds.

**Step 4: Record build metadata**

Record image tag, Python version, extension suffix, sha256, and source leak check result in `docs/verification/k100/molp-pc-binary-build.md`.

**Step 5: Commit**

```bash
git add model/MolP-PC/binary_delivery/scripts/build_binary_bundle.sh docs/verification/k100/molp-pc-binary-build.md
git commit -m "docs: record molp-pc k100 binary build"
```

### Task 5: Run MolP-PC Binary Smoke Test On K100

**Files:**
- Create: `docs/verification/k100/molp-pc-binary-smoke.md`

**Step 1: Upload only the binary bundle**

Upload `dist/molp-pc-k100-binary.tar.zst` to the commercial test machine. Do not upload `model/MolP-PC/src`, `model/MolP-PC/predict/*.py`, build scripts, or generated `.c` files.

**Step 2: Extract inside the running container**

```bash
mkdir -p /opt/sciminer/models/molp-pc
tar --use-compress-program=unzstd -xf molp-pc-k100-binary.tar.zst -C /opt/sciminer/models/molp-pc
```

Expected: extracted package contains only approved files.

**Step 3: Run platform entry**

```bash
bash /opt/sciminer/models/molp-pc/platform_run.sh \
  --task-id k100-molp-pc-binary-smoke \
  --input-dir /opt/sciminer/models/molp-pc/examples/sample_input \
  --output-dir /tmp/sciminer/molp-pc-output \
  --params-json /opt/sciminer/models/molp-pc/examples/request.legacy.json \
  --work-dir /tmp/sciminer/molp-pc-work \
  --device cpu
```

Expected: `result.json`, logs, and standard properties Artifact are produced.

**Step 4: Record the result**

Record command, duration, stdout/stderr summary, `result.json`, produced Artifact paths, and any DTK/K100 operator warnings.

**Step 5: Commit**

```bash
git add docs/verification/k100/molp-pc-binary-smoke.md
git commit -m "docs: record molp-pc k100 binary smoke test"
```

### Task 6: Expand The Compatibility Matrix

**Files:**
- Create: `docs/verification/k100/model-compatibility-matrix.md`

**Step 1: Create the matrix**

Use this table shape.

```markdown
| Model | Priority | Delivery Mode | Python | K100 Dependency Status | Smoke Status | Artifact Contract | Blocker | Next Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MolP-PC | P0 | .so + thin entry | 3.11 target | TBD | TBD | TBD | TBD | Build binary template |
| MSIGN | P1 | TBD | TBD | TBD | TBD | TBD | TBD | Probe deps |
| Pocket2Mol | P2 | TBD | TBD | TBD | TBD | TBD | TBD | Probe deps |
| GCDM | P2 | TBD | TBD | TBD | TBD | TBD | TBD | Probe deps |
| LVpocket | P3 | TBD | TBD | TBD | TBD | TBD | TBD | Probe deps |
| MMCD | P3 | TBD | TBD | TBD | TBD | TBD | TBD | Probe deps |
| TheraPainter | P3 | TBD | TBD | TBD | TBD | TBD | TBD | Probe deps |
```

**Step 2: Update after each model probe**

Every model must record dependency status, smoke status, Artifact contract status, blocker, and next action.

**Step 3: Commit**

```bash
git add docs/verification/k100/model-compatibility-matrix.md
git commit -m "docs: add k100 model compatibility matrix"
```

