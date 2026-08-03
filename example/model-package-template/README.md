# Model Package Template

This is a reusable model-side package template for SciMiner model deployment work.

Use it when you receive raw model code and weights and need to organize them before creating a
Tool Package v2. The template keeps the raw model implementation behind a small runtime wrapper
so Codex or Claude can adapt inputs and outputs without changing platform code.

## What This Template Provides

- A fixed model-side layout.
- A thin model-side `platform_run.sh` adapter entrypoint that accepts runner-level arguments such
  as `--model-root` and delegates to the runtime CLI.
- A testable runtime wrapper under `src/model_runtime_template/`.
- Runtime Env metadata for container-first execution and conda-pack fallback.
- Example request and output files.
- Agent instructions for future model cleanup tasks.
- Git ignore rules that keep weights and machine-specific files out of source control.

## Runtime Policy

The template treats the model runtime as a versioned artifact. `MODEL_PACKAGE.yaml` declares the
preferred container image by digest and a conda-pack fallback for executors that cannot run
containers. Executors mount inputs, outputs, work directories, and weights, then call the
model-side `platform_run.sh` adapter entrypoint; they do not install dependencies during task
execution.

## Quick Check

```bash
pytest example/model-package-template/tests/test_model_package_runtime_contract.py \
  test/test_model_package_template.py -q
```

This checks the package structure and output wrapping logic only. It does not validate any real
scientific model.
