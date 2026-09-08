# AT-003 平台工具调用真实运行记录模板

> 用途：记录一次 `PubChem -> Ligand Preparation -> RDKit -> MolP-PC` 平台 smoke 的真实证据。此模板只记录平台任务链路，不得记录 `model/MolP-PC/platform_run.sh` 作为验收结果。

## 1. 环境信息

| 字段 | 记录值 |
| --- | --- |
| 验收日期 | YYYY-MM-DD |
| 平台环境 | dev / lab / demo / prod-like |
| 后端版本或 commit |  |
| 前端版本或 commit |  |
| 任务后端 | direct / celery |
| 文件存储 | local / minio |
| 操作人 |  |

## 2. 输入记录

| 字段 | 记录值 |
| --- | --- |
| 项目 ID |  |
| WorkflowDefinition ID |  |
| WorkflowRun ID |  |
| PubChem 输入 | CID / name / SMILES |
| input_sha256 |  |
| 离线输入 ArtifactVersion | 如无则填 N/A |

## 3. MolP-PC 平台任务记录

| 字段 | 记录值 |
| --- | --- |
| 工具 slug | molp-pc-property-prediction |
| ToolVersion | 0.1.1 |
| tool_version_id |  |
| task_id |  |
| 调度模式 | direct / celery |
| 调度队列 | 如无则填 N/A |
| 标准输入绑定 | molecules -> ArtifactVersion ID |
| 任务状态 | success / failure / canceled |
| 失败诊断 | 如成功则填 N/A |

## 4. 输出 Artifact 记录

| 输出 | 标准类型 | ArtifactVersion | artifact_version_id | 文件 role / checksum |
| --- | --- | --- | --- | --- |
| properties | molecule_table@1 |  |  | table_file / metadata_json |
| report | run_report@1 |  |  | report_json / report_markdown |

## 5. 科学元数据核对

| 字段 | 预期 | 实际 |
| --- | --- | --- |
| model_name | MolP-PC |  |
| model_version | 0.1.1 |  |
| endpoint_ref | 与 Tool Package 声明一致 |  |
| runtime_ref | 与 Tool Package 声明一致 |  |
| weights_ref | 与 Tool Package 声明一致 |  |
| evidence_level | engineering_smoke_only |  |
| applicability_domain_status | unknown 或模型实际输出 |  |
| unit_or_label_policy | per_endpoint_definition_or_unknown |  |
| model_card_ref | 存在 |  |
| verification_record_ref | 存在 |  |

## 6. 下载与审计

| 检查项 | 记录值 |
| --- | --- |
| 任务详情可打开 | yes / no |
| Artifact 详情可打开 | yes / no |
| properties 文件可下载 | yes / no |
| report 文件可下载 | yes / no |
| FILE_DOWNLOAD 审计存在 | yes / no |
| 跨项目访问被拒绝 | yes / no / N/A |

## 7. 结论

| 字段 | 记录值 |
| --- | --- |
| 验收结论 | pass / fail |
| 阻断问题 | 如无则填 N/A |
| 后续动作 | 如无则填 N/A |

## 8. 附件

- 任务详情截图：
- Workflow 运行截图：
- Artifact 详情截图：
- 下载文件清单：
- 相关日志片段：
