# MolP-PC Model Card

## Intended Use

MolP-PC is the selected V1 delivery tool family for Basic ADMET Prediction and ADMET-related molecular property prediction on molecule tables with a `SMILES` identifier column.

## Delivery Identity

- Tool slug: `molp-pc-property-prediction`
- Model version: `0.1.1`
- Endpoint/runtime reference: `local_runtime:molp-pc-property-prediction@0.1.1`
- Runtime image digest: `registry.example/sciminer/molp-pc-runtime@sha256:4444444444444444444444444444444444444444444444444444444444444444`
- Weights manifest: `artifacts://model-weights/molp-pc-property-prediction/0.1.1/weights.json#sha256:6666666666666666666666666666666666666666666666666666666666666666`

## Interpretation Boundary

The package exposes Basic ADMET Prediction outputs as `molecule_table@1` plus `run_report@1`. Endpoint units or labels are interpreted per endpoint definition when available; otherwise they must remain `unknown` and must not be treated as experimental measurements.

## Evidence Level

Current packaged evidence level is `engineering_smoke_only`. This is sufficient for platform contract validation and demo routing, but it is not scientific validation.
