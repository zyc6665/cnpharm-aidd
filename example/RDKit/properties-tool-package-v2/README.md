# RDKit Molecular Properties Tool Package v2

这个示例工具使用 RDKit 计算常用小分子描述符，并通过平台固定的 Tool Package v2
契约输出标准 `molecule_table@1` 和 `run_report@1`。

## 标准契约

- 输入：`molecules`，类型 `molecule_table@1`
- 输出：`properties`，类型 `molecule_table@1`
- 输出：`report`，类型 `run_report@1`

Tool Package runner 只负责把平台参数转交给模型侧 `platform_run.sh`。RDKit 依赖和
描述符计算逻辑位于 `model/RDKitProperties`，Executor 不在任务执行期间安装依赖。
