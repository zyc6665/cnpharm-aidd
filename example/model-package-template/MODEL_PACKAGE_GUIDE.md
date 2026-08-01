# Model Package Guide

这个目录是模型侧规范包模板。它解决的是“拿到原始模型代码和权重后，如何把模型源码整理成
可交给平台 Tool Package 继续适配的规范包”。

## 核心原则

平台契约固定，模型侧包负责适配输入、输出和运行方式。不要修改平台后端或前端来适配单个模型。

## 目录约定

- `original_model/`：放原始模型代码。除必要兼容修复外，不在这里写平台逻辑。
- `weights/`：放本地权重。真实权重不提交 Git，只保留 `WEIGHTS.md`。
- `src/model_runtime_template/`：标准 runtime wrapper，负责输入解析、原始模型调用、结果收敛和 CLI。
- `platform_run.sh`：部署入口，只解析通用任务参数并调用 runtime CLI。
- `examples/`：最小输入输出样例，供合同测试和人工 smoke test 使用。
- `tests/`：不依赖重模型环境的模型包结构与结果收敛测试。
- `MODEL_PACKAGE.yaml`：模型侧元数据和标准输入输出声明。

## 适配步骤

1. 把原始模型源码放入 `original_model/`，把权重放入 `weights/`。
2. 修改 `MODEL_PACKAGE.yaml` 的 `slug`、`name`、`version`、`legacy_entrypoint` 和标准契约。
3. 在 `legacy_predict.py` 里调用原始模型入口，只在这里处理模型私有参数和文件布局。
4. 在 `result_builder.py` 里把原始输出收敛为 `aidd.sciminer/result.v2`。
5. 保持 `platform_run.sh` 是薄入口，不写死账号、主机、容器名或宿主机路径。
6. 补充 `tests/test_model_package_runtime_contract.py`，至少覆盖输入校验、输出收敛和忽略规则。

## 与 Tool Package v2 的关系

模型侧规范包不替代 `example/model-platformization-template` 或实际 Tool Package v2。建议流程是：

1. 先把原始模型整理成这个模型侧规范包。
2. 再把模型侧规范包封装成 `tool-package-v2`。
3. 平台只消费标准 Artifact 类型和 `result.v2`。

## 验证

从仓库根目录运行：

```bash
pytest example/model-package-template/tests/test_model_package_runtime_contract.py \
  test/test_model_package_template.py -q
```

如果没有完整依赖和权重，只运行合同测试，不声明模型科学结果已验证。
