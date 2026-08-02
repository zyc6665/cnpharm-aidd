# Pocket2Mol Model Runtime Package

这个包是 Pocket2Mol 的模型侧平台化 runtime。平台只下发标准 `request.v1` 并收取
`result.v2`；本包负责把 `binding_pocket@1` 输入适配为旧 Pocket2Mol 所需的
`input_files.protein_pdb` 与 `center` 参数，再把旧模型输出收敛为标准分子表和配体结构。

真实部署时通过 `POCKET2MOL_LEGACY_ENTRYPOINT` 指向原始模型入口。该路径属于部署环境配置，
不写入平台契约。
