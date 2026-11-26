# LDDM Tool Package v2

将 `LPDI-EPFL/lddm` 口袋条件 3D 分子生成模型封装为平台标准 `ToolPackage v2` 交付包。

- 标准输入：`protein_pdb`（`protein_structure@1`，必填）与 `pocket`（`binding_pocket@1`，可选；也可由 `center_x/y/z` 指定）
- 标准输出：`molecules`（`molecule_table@1`，含 9 项 RDKit 理化描述符与 Murcko 骨架）、`ligands`（`ligand_structure@1`）、`report`（`run_report@1`）
- 运行形态：`k8s_job`，`lddm.ckpt` 已随镜像打包，无需宿主机外挂权重目录。
