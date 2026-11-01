# MolP-PC Platformization Instructions

本包用于把 MolP-PC 旧模型部署为平台 Tool Package v2。修改时请遵守：

- 平台契约固定；不要修改平台后端或前端来适配 MolP-PC。
- 不要新增 `smiles_csv`、`admet_csv`、`property_result` 等私有主路径 Artifact 类型。
- 新工具主路径使用 `molecule_table@1` 输入和 `molecule_table@1` 输出。
- 运行设备属于 variant 执行上下文，不要把 `device` 设为必填业务参数。
- `tool.yaml.runtime` 必须声明 Runtime Env、镜像 digest、conda-pack fallback、权重 manifest 和缓存 key。
- Executor 不安装依赖，不依赖宿主机私有 conda 路径。
- 不要提交账号、凭据、私有地址、宿主机绝对路径或大模型权重副本。
- 未完成真实硬件黄金样例前，variant 保持 `unvalidated`。

适配真实代码时，优先只改 runner 和 adapter：

- 输入处理：标准 request `inputs.molecules.files.table_file` -> 旧模型需要的 SMILES CSV。
- 模型执行：调用旧 `predict/test.py::predict(path, name)` 或既有脚本。
- 输出处理：旧 `cb_data_result.csv` -> `properties: molecule_table@1`。
