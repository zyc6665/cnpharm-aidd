# Tool Package template

This directory is a runnable reference for Tool Package v1. Replace the scientific
implementation in `runner/tool_impl.py`, keep the input/output contract explicit,
and retain contract tests for every hardware variant.

Validate from `backend/`:

```bash
python -m app.tool_packages.validator ../example/tool-package-template
```

Run the local contract test from the repository root:

```bash
pytest example/tool-package-template/tests/test_contract.py -q
```

The included implementation emits structurally valid empty pocket results only. It
is a contract smoke test, not a scientific implementation or validation claim.
