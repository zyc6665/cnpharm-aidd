# Model Package Template Agent Instructions

本目录用于把原始模型代码整理成模型侧规范包。执行任务时遵守：

- 平台契约固定；不要修改平台后端或前端来适配模型。
- 只在模型包目录内修改源码、runtime wrapper、样例、测试和文档。
- 不要提交真实权重、wheelhouse、缓存、运行输出、私有部署配置或凭据。
- `platform_run.sh` 必须保持薄入口，只委托到 runtime CLI。
- `MODEL_PACKAGE.yaml.runtime` 必须声明 container 优先、conda-pack fallback、执行器支持和缓存策略。
- Executor 不安装依赖，也不依赖宿主机私有 conda 路径。
- runtime wrapper 必须可测试，轻量测试不能依赖真实 GPU 或大权重。
- `result_builder.py` 是原始模型输出到平台 `result.v2` 的唯一收敛点。

复制本模板后，先改 `MODEL_PACKAGE.yaml`，再改 `legacy_predict.py` 和
`result_builder.py`，最后更新测试和样例。
