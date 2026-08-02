# MolP-PC Tool Package v2 Example

这个示例把 `model/MolP-PC` 的旧式 `ssh_job` 交付整理为平台 Tool Package v2。
它不是重新训练或重写 MolP-PC，而是在旧模型外包一层输入/输出 adapter，让平台只面对稳定
Artifact 契约。

## 标准契约

- 输入：`molecules: molecule_table@1`
  - `table_file` 必须是 CSV，并包含 `SMILES` 列。
  - `metadata_json` 描述输入表，`molecule_id_field` 使用 `SMILES`。
- 输出：`properties: molecule_table@1`
  - `table_file` 为 MolP-PC ADMET 预测结果 CSV。
  - `metadata_json` 记录行数、属性列数量、属性列名和来源任务。
- 可选输出：`report: run_report@1`
  - `report_json` 记录 adapter 状态和摘要。

## 适配策略

旧交付中的 `platform_run.sh` 会产生旧格式 `output/result.json` 和
`output/artifacts/cb_data_result.csv`。本 v2 示例把真正对平台有意义的预测 CSV 收敛为
`molecule_table@1`，不再让 Agent 或 workflow 处理 `smiles_csv`、`prediction_file` 这类
模型私有字段。

部署真实模型时可以保留旧 `predict/test.py::predict(path, name)`，但适配逻辑属于
`model/MolP-PC/src/molp_pc_runtime`，不是平台 Tool Package：

1. 从平台标准 request 的 `inputs.molecules.files.table_file` 找到 SMILES CSV。
2. 模型运行结束后由 `molp_pc_runtime.result_builder` 把 `cb_data_result.csv` 包装为 result.v2。

## Runtime Env

`tool.yaml.runtime` 声明 MolP-PC 的运行环境产物：Python 3.8、CUDA 11.3、首选 container
镜像 digest、conda-pack fallback、权重 manifest SHA-256 和缓存 key。Executor 不安装依赖，
也不依赖宿主机私有 conda 路径；部署时只选择 manifest 中已验证的 Runtime Env。

## 为什么使用 molecule_table@1

MolP-PC 的输入和输出本质都是分子表。输入表至少包含 `SMILES`，输出表是在同一分子 ID 上追加
ADMET 属性列。因此两侧统一为 `molecule_table@1`，比新增 `smiles_csv` 或
`admet_prediction_csv` 更适合平台统一编排、存储、校验和可视化。

## 验证命令

从仓库根目录运行：

```bash
pytest test/test_molp_pc_tool_package_v2.py \
  model/MolP-PC/tests/test_molp_pc_runtime_contract.py -q
```

从 `backend/` 运行平台 manifest 校验：

```bash
python -m app.tool_packages.validator ../example/MolP-PC/tool-package-v2
```

这些命令只验证平台契约和样例结构，不代表模型科学结果或硬件兼容已完成验证。
