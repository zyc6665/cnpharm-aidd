# Pocket2Mol Tool Package v2

这个工具包把 Pocket2Mol 口袋配体生成模型适配到 SciMiner 固定平台契约。

## 标准契约

- 输入：`pocket`，类型 `binding_pocket@1`
- 输出：`molecules`，类型 `molecule_table@1`
- 输出：`ligands`，类型 `ligand_structure@1`，多文件
- 输出：`report`，类型 `run_report@1`

## 运行边界

Tool Package 只负责声明标准 Artifact、参数和 runner 入口。Pocket2Mol 的旧字段转换、中心点推导、SDF 拆分和 `result.v2` 生成由模型侧 `model/Pocket2Mol/src/pocket2mol_runtime` 完成。
