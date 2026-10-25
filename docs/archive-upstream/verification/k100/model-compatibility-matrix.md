# K100 Model Compatibility Matrix

Last updated: 2026-08-06

| Model | Priority | Delivery Mode Tested | Python | CPU Smoke | DCU Smoke | Artifact Contract | Primary Blocker | Next Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MolP-PC | P0 | Raw restored bundle | 3.8.20 restored; 3.11 target | Passed | Failed | Passed | No DTK/HIP-compatible DGL GPU build | Keep CPU package usable; evaluate vendor DGL or DTK/HIP port. |
| MSIGN | P1 | Raw restored bundle | 3.9.21 restored | Passed | Failed | Passed | Restored PyTorch/DGL is NVIDIA CUDA 11.3 ABI | Keep CPU package usable; depends on DTK/HIP DGL path. |
| LVpocket | P2 | Raw restored bundle | 3.10.20 restored | Passed | Failed | Passed | Restored TensorFlow is CUDA/NVIDIA and cannot see DCU | Keep CPU path; check Hygon/DTK TensorFlow availability. |
| Pocket2Mol | P2 | Raw restored bundle | 3.10.12 restored; 3.11 target | Passed | Failed | Passed | PyG stack is CUDA 12.4/NVIDIA ABI; DTK PyTorch lacks PyG extensions | Rebuild PyG extensions against DTK PyTorch 2.7.1 if DCU is required. |
| GCDM | P3 | Not covered by this four-model report | TBD | TBD | TBD | TBD | TBD | Run after four-model CPU/platform path is stabilized. |
| MMCD | P3 | Not covered by this four-model report | TBD | TBD | TBD | TBD | TBD | Run after smaller models are stable. |
| TheraPainter | P3 | Not covered by this four-model report | TBD | TBD | TBD | TBD | TBD | Run after smaller models are stable. |

