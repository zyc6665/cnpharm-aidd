# GCDM Model Runtime Package

这个包是 GCDM 的模型侧平台化 runtime。平台只下发标准 `request.v1` 并收取
`result.v2`；本包负责把 `binding_pocket@1` 输入适配为旧 GCDM 所需的
`input_files.pocket_pdb`，再把旧模型输出的 SDF/SMILES 文件收敛为标准分子表和配体结构。

真实部署时通过 `GCDM_LEGACY_ENTRYPOINT` 指向原始模型入口。该路径属于部署环境配置，
不写入平台契约。
