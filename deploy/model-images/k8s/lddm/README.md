# LDDM 模型计算镜像（`compute-lddm`）

基于 `LPDI-EPFL/lddm`（Large Drug Discovery Model）封装的 K8s 计算镜像与平台适配入口。

- 上游仓库：<https://github.com/LPDI-EPFL/lddm>（MIT）
- 预训练权重：`lddm.ckpt`（Zenodo #22754501，约 160.5 MB，`CD+BB+BN` 主权重，CC-BY-NC 4.0）或可替换为 `lddm_CDBB.ckpt`（MIT）。
- 入口适配：[lddm_platform.py](lddm_platform.py) + [platform_run.sh](platform_run.sh)，支持：
  1. 直接传入 `--ref_ligand` SDF，或由平台 `pocket_pdb` / `(center_x, center_y, center_z)` 自动生成 3D 探针 SDF 供 `extract_pocket_residues` 切出口袋；
  2. 原生 `--n_samples`、`--batch_size` GPU 批并行采样、`--n_steps`、`--sampler`、`--sampling_noise`、`--molecule_size`、`--seed`；
  3. 产物通过共享 `platform_adaptor/postprocess_result.py --model lddm` 统一产出带 9 项 RDKit 理化描述符与 Murcko 骨架的 `molecule_table@1` + `ligand_structure@1` + `run_report@1`。

## 在 4090 上构建与推送

先准备构建上下文目录（包含上游 `repo/` + `checkpoints/lddm.ckpt`、`platform_adaptor/`、`lddm_platform.py`、`platform_run.sh`）：

```bash
docker build \
  -f deploy/model-images/k8s/lddm/Dockerfile \
  -t 127.0.0.1:30500/aidd/compute-lddm:1.0.0 \
  /data/liudh/lddm-build
docker push 127.0.0.1:30500/aidd/compute-lddm:1.0.0
docker inspect --format='{{json .RepoDigests}}' 127.0.0.1:30500/aidd/compute-lddm:1.0.0
```
