# AT-003 平台工具调用 smoke 验收说明

> 状态：主验收操作说明。本文用于 V1 小分子 ADMET 链路联调和交付前复核，验收路径必须经过平台注册工具、任务创建、执行器网关和标准 Artifact 持久化。

## 目标链路

```text
Fetch PubChem Ligand
  -> Ligand Preparation
  -> SDF to SMILES Table
  -> RDKit Properties
  -> MolP-PC Basic ADMET
```

本 smoke 验证平台工具调用、Artifact 绑定、Result Manifest、任务详情和结果可定位性。RDKit Properties 只是理化描述符步骤，不替代 MolP-PC 基础 ADMET。

## 平台调用口径

- MolP-PC 必须通过平台注册工具 `molp-pc-property-prediction` 调用。
- 平台任务必须使用该工具的当前 `ToolVersion`，并经由 `create_and_schedule_tool_task` 创建普通平台任务。
- 调度入口必须进入 Executor Gateway 支持的后端；开发环境可用 direct backend，交付演示和多人环境应使用 Celery + Redis。
- 不得以 `model/MolP-PC/platform_run.sh` 作为平台验收主路径。该脚本只用于模型包本地调试、runtime 依赖自检或执行器镜像排障。
- 任务输出必须回到平台 `TaskOutput`、标准 ArtifactVersion、文件下载权限和审计链路。

## 前置条件

- 后端、Worker、队列和文件存储按目标环境启动；开发单人联调可临时使用 direct backend。
- 前端可访问后端 API，测试账号可登录并创建或进入项目。
- 数据库已完成迁移和工具初始化，至少包含 `builtin-fetch-ligand`、`ligand-preparation`、`builtin-sdf-to-smiles-csv`、`builtin-rdkit-properties`、`molp-pc-property-prediction`。
- `molp-pc-property-prediction` 的当前 `ToolVersion` 固定为 `0.1.1`，工具配置包含 runtime、weights、endpoint/runtime 标识和标准输入输出契约。
- PubChem 查询可访问外网；离线环境需提前准备等价的 `ligand_structure@1` 输入 Artifact。

## 操作步骤

1. 登录平台，进入一个项目空间。
2. 打开工作流画布，选择 `PubChem -> ADMET` 预设。
3. 在 Fetch PubChem 节点输入小分子标识；推荐 smoke 样例为 PubChem CID `2244`。
4. 运行工作流，等待所有工具节点完成。
5. 打开 MolP-PC 节点任务详情，确认任务工具 slug 为 `molp-pc-property-prediction`，工具版本为 `0.1.1`。
6. 确认 MolP-PC 任务存在 `tool_version_id`、调度信息和 `molecules` 标准 Artifact 输入绑定。
7. 确认输出区出现科学附件引用：模型卡、验证记录、证据等级。
8. 下载 MolP-PC 输出文件，至少包含 ADMET/性质表格、metadata JSON 和 `run_report@1` 报告文件。
9. 从工作流节点跳转任务中心，确认节点任务可按 workflow/run/node 上下文筛选定位。

## 通过标准

- 用户不需要手动填写文件路径、file_id 或 ArtifactVersion ID。
- Fetch PubChem 产出 `ligand_structure@1`，Ligand Preparation 保留标准配体结构。
- SDF to SMILES 和 RDKit Properties 均产出 `molecule_table@1`，表格中保留可供下游使用的 SMILES。
- MolP-PC 节点消费 RDKit Properties 的 `properties` ArtifactVersion，并产出 `molecule_table@1` 与 `run_report@1`。
- MolP-PC 结果显示模型版本、runtime/endpoint 标识、单位或标签策略、证据等级、模型卡引用和验证记录引用。
- 下载行为走受保护文件下载入口，任务详情和任务中心能定位失败原因或输出文件。
- 失败值不得用 0 填充；未评估适用域必须标记为 `unknown`。
- 真实验收记录使用 [AT-003 平台工具调用真实运行记录模板](./templates/at003-platform-tool-run-record.md) 填写 task_id、ToolVersion、输入哈希和输出 ArtifactVersion。

## 失败排查

| 现象 | 优先检查 |
| --- | --- |
| PubChem 节点失败 | 外网访问、输入 CID/名称/SMILES、外部数据库超时日志。 |
| Ligand Preparation 无 3D | RDKit/OpenBabel 依赖、构象生成日志、输出 role。 |
| MolP-PC 未被调度 | RDKit 输出是否存在 `molecule_table@1`，工作流定义中 `molecules` 是否绑定到 `node:<rdkit>:properties`。 |
| MolP-PC 调度到了非目标工具 | Planner、工作流预设和工具版本是否仍指向 `molp-pc-property-prediction`。 |
| MolP-PC 任务没有 `tool_version_id` | 是否绕过了 `create_and_schedule_tool_task` 或使用了非平台脚本路径。 |
| MolP-PC 输出无科学附件引用 | 任务 `outputs.result.standard_result.artifacts.report.metadata` 是否包含 `model_card_ref` 和 `verification_record_ref`。 |
| 输出可下载但下游不能用 | Result Manifest role、checksum、Artifact type 与 tool contract 是否一致。 |

## 自动化回归

交付前至少运行以下回归，证明平台计划、任务调度、Artifact 绑定、后端校验和任务结果展示仍可用：

```bash
python -m pytest "test/test_aidd_agent_planner.py" \
  "test/test_workflow_scheduler.py" \
  "test/test_workflow_validation_standard_artifacts.py" \
  "test/test_tasks_service_standard_inputs.py" \
  "test/test_delivery_docs.py" -q
```

```bash
npm --prefix "frontend" test -- \
  "test/workflow-canvas-presets.test.ts" \
  "src/composables/useWorkflowCanvas.spec.ts" \
  "src/domain/tasks/output-summary.spec.ts" \
  "src/components/tasks/TaskOutputSummary.spec.ts"
```
