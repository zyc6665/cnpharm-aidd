# Four-Model K100/DCU Compatibility Test Report

## Source

- Source file: `model/四个模型国产化信创平台测试报告.docx`
- Report date: 2026-08-06
- Test environment: Hygon DCU domestic platform container
- Base image: `harbor.sourcefind.cn:5443/dcu/admin/base/pytorch:2.7.1-ubuntu22.04-dtk26.04-py3.11`

## Environment Summary

| Item | Result |
| --- | --- |
| System Python | `/usr/local/bin/python3`, Python 3.11.9 |
| Main PyTorch | `2.7.1` / `2.7.1+das.opt1.dtk2604` |
| HIP/DTK | HIP `6.3.26093`, DTK `26.04` |
| DCU device | `K100_AI` |
| PyTorch DCU visibility | `torch.cuda.is_available() == True` |
| PyTorch arch list | `gfx906`, `gfx926`, `gfx928`, `gfx936`, `gfx938` |

The main container environment can see the K100 DCU through DTK PyTorch. The DCU
failures below are caused by model-specific restored environments or third-party
GPU extension ABI mismatches, not by the hardware being invisible.

## Overall Result

| Model | Task Type | CPU Smoke | DCU Smoke | Main Conclusion |
| --- | --- | --- | --- | --- |
| MolP-PC | Molecular property prediction | Passed | Failed | CPU inference works; DCU is blocked by DGL CPU-only or non-DTK GPU builds. |
| MSIGN | Protein-ligand affinity prediction | Passed | Failed | CPU inference works; restored environment is NVIDIA CUDA/DGL, not DTK/HIP. |
| LVpocket | Protein pocket prediction | Passed | Failed | CPU execution works; restored TensorFlow is CUDA/NVIDIA and cannot see DCU. |
| Pocket2Mol | Pocket-conditioned ligand generation | Passed | Failed | CPU entry and model loading work; restored PyG stack is CUDA 12.4/NVIDIA ABI. |

Current deliverable state should be recorded as: **CPU compatible, DCU not yet
compatible**.

## Model Findings

### MolP-PC

- Restored environment: `/workspace/molp-pc`, Python 3.8.20.
- Smoke script: `/workspace/MolP-PC/scripts/run_smoke_test.sh`.
- CPU output: `output/artifacts/cb_data_result.csv`, shape `2 x 56`.
- CPU conclusion: input parsing, RDKit processing, weight loading, inference, and
  CSV export are usable.
- DCU blocker: current Python 3.11 environment uses CPU `dgl==1.1.3`; NVIDIA CUDA
  DGL wheels are not a valid DTK/HIP solution and can segfault during graph move
  to `cuda:0`.
- Deep blocker: DGL requires real DTK/HIP source-level porting or a vendor-provided
  compatible build.

### MSIGN

- Restored environment: `/workspace/msign-runtime/MSIGN`, Python 3.9.21.
- Key dependencies: `torch==1.12.1`, `dgl==0.9.1`, `dgllife==0.3.0`,
  `rdkit==2024.09.1`, `scikit-learn==0.24.2`.
- Smoke script: `/workspace/MSIGN/scripts/run_smoke_test.sh`.
- CPU output includes `result.json`, `prediction.json`, `run.log`, generated pocket
  PDB, RDKit output, and DGL graph artifacts.
- CPU result includes `predicted_affinity = -11.099943161010742`.
- DCU blocker: restored PyTorch/DGL stack is NVIDIA CUDA 11.3 ABI and reports
  `torch.cuda.is_available = False` on K100.

### LVpocket

- Restored environment: `/workspace/LVpocket-2/env`, Python 3.10.20.
- Key dependencies: TensorFlow 2.15.1, Keras 2.15.0, OpenBabel 3.1.0.
- Smoke script: `/workspace/LVpocket-2/scripts/run_smoke_test.sh`.
- CPU output includes `output/result.json`, `output/artifacts/prediction.json`,
  `output/logs/run.log`, and `output/artifacts/lv_results/input/pockets.cmap`.
- CPU smoke uses `model_choice=all`; `pocket_count=0` is acceptable for this smoke
  test because the target is runtime and artifact validation, not accuracy.
- DCU blocker: restored TensorFlow is CUDA/NVIDIA build and reports no GPU devices
  on Hygon DCU.

### Pocket2Mol

- Restored environment: `/workspace/Pocket2Mol-h100`, Python 3.10.12.
- Key dependencies: `torch==2.4.1`, `torch_geometric==2.3.1`, PyG extensions built
  as `pt24cu124`, `rdkit==2026.03.1`.
- Smoke script: `/workspace/Pocket2Mol-main/scripts/run_smoke_test.sh`.
- CPU smoke uses small parameters: `num_samples=1`, `beam_size=1`, `max_steps=1`,
  `device=cpu`.
- CPU output includes `result.json`, `sample.log`, `platform_sample_config.yml`,
  `metadata.csv`, `run_info.json`, and `SMILES.txt`.
- DCU blocker: restored PyG stack is CUDA 12.4/NVIDIA ABI. The system DTK Python
  can see K100 through PyTorch 2.7.1, but lacks `torch_geometric`, `torch_scatter`,
  `torch_sparse`, `torch_cluster`, and `torch_spline_conv` built for DTK PyTorch.

## Dependency Blocker Categories

| Dependency Type | Affected Models | Current Status | Required Follow-Up |
| --- | --- | --- | --- |
| DGL GPU | MolP-PC, MSIGN | CPU or NVIDIA CUDA ABI only | Need DTK/HIP-compatible DGL build. |
| TensorFlow GPU | LVpocket | CUDA/NVIDIA TensorFlow cannot see DCU | Need DTK/HIP TensorFlow or CPU-only acceptance. |
| PyTorch Geometric GPU | Pocket2Mol | PyG extensions are `pt24cu124` NVIDIA ABI | Rebuild PyG stack against DTK PyTorch 2.7.1. |
| CPU chemistry/visualization deps | MSIGN, LVpocket, Pocket2Mol | CPU imports usable | Not the main DCU blocker. |

## Recommended Next Actions

1. Define the current test milestone as **CPU smoke passed for four models; DCU
   compatibility failed due to third-party GPU extension ABI gaps**.
2. Keep K100 platform testing focused on CPU smoke and platform contract validation
   until DGL/TensorFlow/PyG DTK builds are available.
3. Do not replace the working DTK PyTorch base environment with CUDA or generic
   ROCm wheels; that would risk breaking the currently visible K100 runtime.
4. For DCU acceleration work, split follow-up by dependency family:
   - DGL DTK/HIP build for MolP-PC and MSIGN.
   - TensorFlow DTK/HIP feasibility for LVpocket.
   - PyG extension rebuild for Pocket2Mol.
5. Continue platform integration using CPU-compatible model packages first, then
   treat DCU acceleration as per-model dependency engineering.
