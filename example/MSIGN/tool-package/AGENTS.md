# MSIGN Platformization Instructions

本包用于把 MSIGN 旧模型部署为平台 Tool Package v2。修改时请遵守：

- 平台契约固定；不要修改平台后端或前端来适配 MSIGN。
- 主路径只使用 `protein_structure@1`、`ligand_structure@1`、`molecule_table@1` 和
  `run_report@1`。
- 运行设备属于 variant 执行上下文，不要把 `device` 设为必填业务参数。
- `tool.yaml.runtime` 必须声明 Runtime Env、镜像 digest、conda-pack fallback、权重 manifest
  和缓存 key。
- Executor 不安装依赖，不依赖宿主机私有 conda 路径。
- 不要提交账号、凭据、私有地址、宿主机绝对路径或大模型权重副本。
- 未完成真实硬件黄金样例前，variant 保持 `unvalidated`。
