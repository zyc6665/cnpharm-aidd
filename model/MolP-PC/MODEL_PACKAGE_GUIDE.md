# MolP-PC Model Package Guide

这个目录是模型侧规范包示例：保留原始 MolP-PC 推理代码和权重放置约定，在外层增加稳定
runtime wrapper。平台契约固定，模型代码负责适配标准输入和输出。

## 目录约定

- `predict/`：原始模型推理代码。除必要兼容修复外，不在这里写平台逻辑。
- `predict/model/`：本地权重目录。`*.pth` 不提交 Git，按 `predict/model/WEIGHTS.md` 放置。
- `src/molp_pc_runtime/`：模型侧标准 wrapper，负责输入解析、旧模型调用、结果收敛和 CLI。
- `platform_run.sh`：部署入口，只解析通用任务参数并调用 `molp_pc_runtime.cli`。
- `examples/`：最小输入输出样例，供合同测试和人工 smoke test 使用。
- `tests/`：不依赖 torch/dgl 的模型包结构与结果收敛测试。

## 接入规则

1. 原始模型入口保持在 `predict/test.py::predict(path, name)`。
2. 平台输入统一视为 `molecules: molecule_table@1`，表格必须包含 `SMILES` 列。
3. 模型输出统一写成 `properties: molecule_table@1`，预测 CSV 放在
   `output/artifacts/properties/molp_pc_predictions.csv`。
4. `output/result.json` 使用 `aidd.sciminer/result.v2`。
5. 设备、远端主机、容器名、账号和路径属于部署环境，不写入模型包源码。
6. 权重、wheelhouse、缓存、运行输出和私有部署配置不进入 Git。

## 验证

从仓库根目录运行轻量合同测试：

```bash
pytest model/MolP-PC/tests/test_runtime_contract.py -q
```

真实模型 smoke test 需要先准备 Python 3.8 环境和 `predict/model/*.pth` 权重，然后运行：

```bash
bash model/MolP-PC/platform_run.sh \
  --task-id task-001 \
  --input-dir model/MolP-PC/examples/sample_input \
  --output-dir /tmp/molp-pc-output \
  --params-json model/MolP-PC/examples/request.legacy.json \
  --work-dir /tmp/molp-pc-work \
  --device cpu
```

如果没有完整依赖和权重，只运行合同测试，不声明模型科学结果已验证。
