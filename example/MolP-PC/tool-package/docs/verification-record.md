# MolP-PC Verification Record

## Scope

This record covers the Tool Package v2 contract sample for `molp-pc-property-prediction` version `0.1.1`.

## Evidence

- Evidence level: `engineering_smoke_only`
- Checked artifact contract: `molecule_table@1` input to `molecule_table@1` and `run_report@1` outputs
- Checked runtime identity: container image digest, conda-pack fallback, and weights manifest references declared in `tool.yaml`
- Checked sample output: two-row ADMET prediction CSV and JSON metadata under `examples/output`

## Boundary

This verification proves platform packaging, routing, and sample result shape only. It is not scientific validation, hardware certification, benchmark evidence, or clinical-use evidence.

## Open Items Before Scientific Promotion

- Register reviewed endpoint definitions with units or labels for every delivered prediction column.
- Attach dataset, metric, threshold, and reviewer evidence before assigning a scientific evidence level above `engineering_smoke_only`.
