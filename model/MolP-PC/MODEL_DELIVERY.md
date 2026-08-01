# MolP-PC Delivery Notes

## Summary

- Tool name: MolP-PC Property Prediction
- Suggested slug: `molp-pc-property-prediction`
- Task type: molecular property / ADMET prediction
- Input: CSV molecule table with a required `SMILES` column
- Output: CSV molecule table with ADMET property columns
- Standard platform contract: `molecule_table@1 -> molecule_table@1 + run_report@1`

## Runtime Entry

- Original model entry: `predict/test.py::predict(path, name)`
- Standardized package entry: `platform_run.sh`
- Runtime wrapper package: `src/molp_pc_runtime`
- Weight directory: `predict/model/`

`platform_run.sh` is intentionally thin. It parses task arguments, sets `PYTHONPATH`, and
delegates to `python -m molp_pc_runtime.cli`.

## Required Inputs

The input table must contain:

| Column | Required | Description |
| --- | --- | --- |
| `SMILES` | yes | Molecule identifier and structure string consumed by MolP-PC |

The standard request should bind this table as `inputs.molecules.files.table_file`.
Legacy params JSON with `input_files.smiles_csv` is still accepted by the wrapper for migration.

## Output Files

Successful runs write:

| Path | Standard role | Description |
| --- | --- | --- |
| `output/result.json` | result envelope | `aidd.sciminer/result.v2` |
| `output/artifacts/properties/molp_pc_predictions.csv` | `table_file` | ADMET prediction table |
| `output/artifacts/properties/metadata.json` | `metadata_json` | Row count, property columns, source task |
| `output/reports/report.json` | `report_json` | Adapter execution summary |
| `output/logs/run.log` | log | Shell and runtime logs |

## Validation Status

The included tests validate package structure and result formatting without loading torch or DGL.
They do not prove scientific correctness or hardware compatibility. Real deployment validation must
record:

- exact model weights and SHA-256 checksums
- runtime environment or image digest
- input sample hash
- output `result.json` and artifact hashes
- CPU/GPU hardware and driver details
- reviewer and validation date

## Known Limits

- The legacy model currently emits all configured ADMET task groups.
- `predict/test.py` remains the scientific implementation and still requires the original runtime
  dependencies.
- Invalid SMILES or molecules that fail graph/3D feature construction are model-level failures.
