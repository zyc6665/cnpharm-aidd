# MolP-PC Model Package

MolP-PC predicts ADMET-related molecular properties from a CSV table containing a
`SMILES` column. This directory is a model-side package: it keeps the original
inference code under `predict/` and adds a small standardized runtime wrapper under
`src/molp_pc_runtime/`.

## Layout

```text
MolP-PC/
├── MODEL_PACKAGE.yaml
├── MODEL_PACKAGE_GUIDE.md
├── README.md
├── admet.yml
├── requirements.txt
├── platform_run.sh
├── src/molp_pc_runtime/
├── predict/
│   ├── test.py
│   ├── model.py
│   ├── process.py
│   ├── build_dataset.py
│   ├── pubchemfp.py
│   ├── Extract3DFeature.py
│   └── model/
├── examples/
└── tests/
```

## Standard Contract

- Input: `molecules: molecule_table@1`
- Output: `properties: molecule_table@1`
- Optional report: `report: run_report@1`

The runtime reads a platform request or legacy params JSON, validates the input molecule table,
invokes `predict/test.py::predict(path, name)`, and writes `output/result.json` as
`aidd.sciminer/result.v2`.

## Runtime

Production deployment treats the Python environment as a versioned Runtime Env artifact, not as a
host-local conda path. `MODEL_PACKAGE.yaml` declares Python 3.8, CUDA 11.3, a preferred container
image by digest, and a conda-pack fallback for executors that cannot run containers.

After the selected Runtime Env is active and model weights are mounted in `predict/model/`, run:

```bash
bash platform_run.sh \
  --task-id task-001 \
  --input-dir examples/sample_input \
  --output-dir /tmp/molp-pc-output \
  --params-json examples/request.legacy.json \
  --work-dir /tmp/molp-pc-work \
  --device cpu
```

Use `MOLP_PC_PYTHON=/path/to/python` only for local debugging when the runtime environment is not
the shell default. Production executors should select the declared Runtime Env and must not install
dependencies during task execution.

## Git Policy

The model package commits code, metadata, examples, and tests. It does not commit:

- `predict/model/*.pth`
- `wheelhouse/*.whl`
- runtime caches and outputs
- machine-specific deployment configuration

Record binary artifact checksums and hardware validation evidence outside Git.
