# MSIGN Tool Package v2 Example

这个示例把 MSIGN 旧式 `ssh_job` 交付整理为平台 Tool Package v2。平台只面对稳定
Artifact 契约，模型侧负责把标准输入转换为旧模型需要的文件布局。

## 标准契约

- 输入：`protein: protein_structure@1`
- 输入：`ligand: ligand_structure@1`
- 输出：`affinity: molecule_table@1`
  - `table_file` 为 MSIGN 亲和力预测 CSV。
  - `metadata_json` 记录行数、属性列、来源任务和模型名。
- 可选输出：`report: run_report@1`

## 适配策略

旧 MSIGN 入口消费 `protein_pdb` 和 `ligand_pdb`，输出旧格式 `result.json`。适配逻辑属于
`model/MSIGN/src/msign_runtime`，模型侧 runtime 只把旧 `outputs.prediction` 收敛为亲和力表，
不把 DGL/RDKit 等预处理中间文件暴露为主链路 Artifact。

## Runtime Env

`tool.yaml.runtime` 声明 MSIGN 的运行环境产物：Python 3.8、CUDA、首选 container 镜像
digest、conda-pack fallback、权重 manifest SHA-256 和缓存 key。Executor 不安装依赖，也不依赖
宿主机私有 conda 路径。

## 验证命令

```bash
pytest test/test_msign_tool_package_v2.py \
  model/MSIGN/tests/test_msign_runtime_contract.py -q
```

```bash
PYTHONPATH=backend python -m app.tool_packages.validator example/MSIGN/tool-package
```
