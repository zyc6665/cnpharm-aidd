# MMCD 示例文件

本目录提供后续平台接入或人工验证时可复用的最小样例。

## 文件

- `params_generate_seq_only.json`：只生成肽序列，不生成 PDB。
- `params_generate_with_structures.json`：生成肽序列并尝试生成 PDB。
- `params_structure_from_fasta.json`：对已有 FASTA 补生成 PDB。
- `input/sequences.fasta`：FASTA 上传样例。

## 说明

- `sampling_steps=50` 用于 smoke test；正式运行建议使用 `1000`。
- `device=cpu` 用于环境验证；正式运行建议使用 CUDA。
- checkpoint 路径是当前整理建议的默认候选，后续可按指定权重替换。

