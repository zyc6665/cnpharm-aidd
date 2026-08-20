# RDKit Molecular Properties Runtime

This model-side package adapts RDKit descriptor calculation to the fixed SciMiner
Tool Package v2 request and result contracts.

## Contract

- Input: `molecules`, standard type `molecule_table@1`
- Output: `properties`, standard type `molecule_table@1`
- Output: `report`, standard type `run_report@1`

The package keeps the platform contract stable. The top-level `platform_run.sh` only parses
runner arguments and delegates to `rdkit_properties_runtime.cli`.

## Runtime dependency

RDKit is loaded lazily by the descriptor backend. If RDKit is unavailable, the runtime exits
non-zero and writes a `result.v2` failure report under the output directory.
