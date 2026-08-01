# Sample Output

`cb_data_result.csv` was generated from `examples/sample_input/smiles.csv` with
the MolP-PC runtime environment using the legacy prediction entrypoint:

```bash
cd predict
MOLP_PC_DEVICE=cpu python -c "import test; test.predict('../examples/sample_input/smiles.csv', 'env_check_sample')"
```
