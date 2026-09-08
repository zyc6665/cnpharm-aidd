# AT-003 本地 direct smoke 验收说明

> 状态：操作说明。本文用于 V1 小分子链路联调和交付前复核，不等同于科学验证报告。

## 目标链路

```text
Fetch PubChem Ligand
  -> Ligand Preparation
  -> SDF to SMILES Table
  -> RDKit Properties
  -> MolP-PC Basic ADMET
```

本 smoke 只验证平台链路、Artifact 绑定、Result Manifest 和结果可定位性。RDKit Properties 是独立理化描述符步骤，不替代 MolP-PC 基础 ADMET。

## 前置条件

- 后端使用本地开发配置启动，`TASK_EXECUTION_BACKEND=direct`。
- 前端可访问后端 API，测试账号可登录并创建或进入项目。
- 数据库已完成迁移和工具初始化，至少包含 `builtin-fetch-ligand`、`ligand-preparation`、`builtin-sdf-to-smiles-csv`、`builtin-rdkit-properties`、`molp-pc-property-prediction`。
- MolP-PC 工具版本固定为 `0.1.1`，运行环境、weights、endpoint/runtime 标识与工具包声明一致。
- 本地 MolP-PC 调试需使用 `admet.yml` 声明的 Python 3.8 / CUDA 11.3 环境；如 shell 默认 Python 不是该环境，需设置 `MOLP_PC_PYTHON`。
- PubChem 查询可访问外网；离线环境需提前准备等价的 `ligand_structure@1` 输入 Artifact。

## 启动方式

```bash
cd /data/zhouyc/cpumodel_sciminer/backend
TASK_EXECUTION_BACKEND=direct python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```bash
cd /data/zhouyc/cpumodel_sciminer/frontend
npm run dev -- --host 0.0.0.0 --port 8585
```

direct 模式只用于本地开发和单人联调。进程重启、热更新或长任务阻塞会影响任务连续性，交付演示和多人环境应使用 Celery + Redis。

## 操作步骤

1. 登录平台，进入一个项目空间。
2. 打开工作流画布，选择 `PubChem -> ADMET` 预设。
3. 在 Fetch PubChem 节点输入小分子标识；推荐 smoke 样例为 PubChem CID `2244`。
4. 运行工作流，等待所有工具节点完成。
5. 打开 MolP-PC 节点任务详情，确认输出区出现科学附件引用：模型卡、验证记录、证据等级。
6. 下载 MolP-PC 输出文件，至少包含 ADMET/性质表格、metadata JSON 和 `run_report@1` 报告文件。
7. 从工作流节点跳转任务中心，确认节点任务可按 workflow/run/node 上下文筛选定位。

## 通过标准

- 用户不需要手动填写文件路径、file_id 或 ArtifactVersion ID。
- Fetch PubChem 产出 `ligand_structure@1`，Ligand Preparation 保留标准配体结构。
- SDF to SMILES 和 RDKit Properties 均产出 `molecule_table@1`，表格中保留可供下游使用的 SMILES。
- MolP-PC 节点消费 RDKit Properties 的 `properties` ArtifactVersion，并产出 `molecule_table@1` 与 `run_report@1`。
- MolP-PC 结果显示模型版本、runtime/endpoint 标识、单位或标签策略、证据等级、模型卡引用和验证记录引用。
- 下载行为走受保护文件下载入口，任务详情和任务中心能定位失败原因或输出文件。
- 失败值不得用 0 填充；未评估适用域必须标记为 `unknown`。

## 失败排查

| 现象 | 优先检查 |
| --- | --- |
| PubChem 节点失败 | 外网访问、输入 CID/名称/SMILES、外部数据库超时日志。 |
| Ligand Preparation 无 3D | RDKit/OpenBabel 依赖、构象生成日志、输出 role。 |
| MolP-PC 未被调度 | RDKit 输出是否存在 `molecule_table@1`，工作流定义中 `molecules` 是否绑定到 `node:<rdkit>:properties`。 |
| MolP-PC 失败并提示缺少 `dgl`、`rdkit` 或 `torch` | 当前 Python 不满足模型 runtime；激活 `admet.yml` 环境或设置 `MOLP_PC_PYTHON` 后重跑。 |
| MolP-PC 输出无科学附件引用 | 任务 `outputs.result.standard_result.artifacts.report.metadata` 是否包含 `model_card_ref` 和 `verification_record_ref`。 |
| 输出可下载但下游不能用 | Result Manifest role、checksum、Artifact type 与 tool contract 是否一致。 |

## 自动化回归

交付前至少运行以下回归，证明画布预设、Artifact 绑定、后端校验和任务结果展示仍可用：

```bash
python -m pytest "test/test_workflow_scheduler.py" "test/test_workflow_validation_standard_artifacts.py" -q
npm --prefix "frontend" test -- "test/workflow-canvas-presets.test.ts" "src/composables/useWorkflowCanvas.spec.ts" "src/domain/tasks/output-summary.spec.ts" "src/components/tasks/TaskOutputSummary.spec.ts"
```
