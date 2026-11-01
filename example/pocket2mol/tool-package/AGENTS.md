# Pocket2Mol Tool Package Maintenance

- Keep the package contract aligned with `binding_pocket@1 -> molecule_table@1 + ligand_structure@1 + run_report@1`.
- Do not put deployment host paths, IP addresses, secrets, or credentials in this example package.
- Keep runner scripts as thin delegation shims. Model-specific conversion belongs in `model/Pocket2Mol/src/pocket2mol_runtime`.
- Do not mark a hardware variant as validated without a real platform inference run for that exact package revision.
