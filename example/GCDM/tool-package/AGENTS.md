# GCDM Tool Package Maintenance

- Keep the platform contract fixed: `binding_pocket@1` in, `molecule_table@1`, `ligand_structure@1`, and `run_report@1` out.
- Do not add deployment host paths, IP addresses, secrets, or environment-specific credentials to this package.
- Keep `runner/platform_run_v2.sh` thin. Model-specific input and output conversion belongs in `model/GCDM/src/gcdm_runtime`.
- Mark hardware variants as validated only after that exact package revision has passed real platform inference on the target hardware.
