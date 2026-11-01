# GCDM Tool Package v2

这个工具包把 GCDM 口袋条件分子生成模型适配到 SciMiner 固定平台契约。

## 标准契约

- 输入：`pocket`，类型 `binding_pocket@1`
- 输出：`molecules`，类型 `molecule_table@1`
- 输出：`ligands`，类型 `ligand_structure@1`，多文件
- 输出：`report`，类型 `run_report@1`

## 运行边界

Tool Package 只声明标准 Artifact、参数与 runner 入口。字段转换、旧模型参数生成、SDF 拆分和 `result.v2` 生成都在模型侧 `model/GCDM/src/gcdm_runtime` 中完成。

## 部署要求

部署时将 `MODEL_PACKAGE_ROOT` 指向模型包目录，并确保模型包里的 `platform_run.sh` 可执行。真实旧模型入口由模型包运行时通过 `GCDM_LEGACY_ENTRYPOINT` 或 `legacy/platform_run.sh` 解析。
