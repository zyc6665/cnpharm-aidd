# Model Platformization Agent Instructions

本目录用于把旧模型代码改造成平台 Tool Package v2。执行时请遵守：

- 平台契约固定；不要修改平台后端或前端来迁就单个模型。
- 只在模型部署包、模型侧 runtime、参数 schema、测试和样例输出中做适配。
- 模型 adapter 必须放在 `model/<Model>/src/<runtime>`，统一入口是
  `model/<Model>/platform_run.sh`。
- Tool Package runner 只能委托模型侧入口，不得包含模型私有推理或转换逻辑。
- 不要新增私有 Artifact 类型；优先使用 `protein_structure@1`、`binding_pocket@1`、
  `molecule_table@1`、`ligand_structure@1`、`run_report@1`。
- 不要重新引入 `semantic_inputs`、`semantic_outputs` 或旧版语义映射作为新工具主路径。
- 不要写入凭据、私有地址、宿主机绝对路径或真实生产样例数据。
- `tool.yaml.runtime` 必须声明 Runtime Env、镜像 digest、fallback SHA、权重 manifest 和缓存 key。
- Executor 不安装依赖，不依赖宿主机私有 conda 路径。
- 硬件没真机验证前，不要把对应 variant 标记为 `validated`。

完成适配时至少提供：

- 可加载的 `tool.yaml`
- 标准 `schemas/result.v2.example.json`
- 能从旧模型输出生成 `output/result.json` 的模型侧 runtime adapter
- 包内契约测试
- README 中记录的输入、输出、假设、限制和验证命令
