# Tool Package v2 Template

This directory is the platform-side Tool Package v2 template for SciMiner model tools.
It declares the standard Artifact contract and delegates execution to a model-side
package. Model-specific input conversion, legacy inference, and output conversion belong
in `model/<Model>/src/<runtime>` and are exposed through `model/<Model>/platform_run.sh`.

The platform contract stays fixed:

- Input: `protein` as `protein_structure@1`
- Output: `pocket` as `binding_pocket@1`
- Optional output: `report` as `run_report@1`

`runner/entrypoint.sh` is intentionally thin. It resolves `MODEL_PACKAGE_ROOT` and then
executes `platform_run.sh` from the model package. Do not add package-local adapters or
legacy model logic here.

Validate from `backend/`:

```bash
python -m app.tool_packages.validator ../example/tool-package-template
```

Run the local contract test from the repository root:

```bash
pytest example/tool-package-template/tests/test_tool_package_v2_contract.py -q
```

Before publishing a real package, replace the example runtime image digest, fallback
environment SHA-256, and weights manifest SHA-256 with deployment artifacts produced by
the model packaging process. Keep hardware variants `unvalidated` until a real golden
sample has run on that hardware.
