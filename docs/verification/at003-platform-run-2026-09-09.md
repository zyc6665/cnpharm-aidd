# AT-003 平台工具调用真实运行记录

> 本记录来自平台 API。不得记录 `model/MolP-PC/platform_run.sh` 作为 AT-003 平台验收结果。

## 1. 平台任务记录

| 字段 | 记录值 |
| --- | --- |
| 项目 ID | 66c0bd5b-b506-4aa2-b4b0-52fa5ffaad6a |
| 工具 slug | molp-pc-property-prediction |
| ToolVersion | 0.1.1 |
| tool_version_id | d7600055-5c80-4992-8763-c7a43a346762 |
| task_id | 507b59bd-36ef-40be-a4a4-dfae271029e2 |
| 调度模式 | direct |
| 调度队列 | N/A |
| 标准输入绑定 | molecules -> bb92b727-ee85-4fa5-b7f5-f15c171d1514 |
| 任务状态 | success |

## 2. 输入与输出哈希

| 字段 | 记录值 |
| --- | --- |
| input_sha256 | artifacts__ligands__ligand_001 SMILES table table_file: 092871959942a5b636410725ccfe0a0f41f920bd71ccc7171ae718dc8fcb3da4; artifacts__ligands__ligand_001 SMILES table metadata_json: 34cbf1b8a478a40408aa4215d525930cddccedeab37ba8fe19c848231d1e146c |
| output_sha256 | logs__run.log: 04c7b87953645f40ae7dc93966755e83b9f941b82a0d45ba595e72d49176d00c; artifacts__cb_data_result.csv: c8035b1c508ae8e62993e2fa139d817500059e8f7f10d1f5f7ee98b5090899f5; artifacts__properties__metadata.json: 2f8ad06c639a444b765a2e867e8e8cb7c0fffbdf5c6aba171a0855a42d1580f7; reports__report.json: d68eebda81ca0029f95f02cbd2ac0a2b97eb66edda9540dfa8df7fbadfa13a58 |

## 3. 输出 Artifact 记录

| 输出 | 标准类型 | ArtifactVersion | artifact_version_id | 文件 role / checksum |
| --- | --- | --- | --- | --- |
| 507b59bd-36ef-40be-a4a4-dfae271029e2_molp_pc_adapter_report | run_report@1 | 1 | de6fb09c-60fc-4298-a939-ada5ae44e02c | report_json: d68eebda81ca0029f95f02cbd2ac0a2b97eb66edda9540dfa8df7fbadfa13a58 |
| 507b59bd-36ef-40be-a4a4-dfae271029e2_molp_pc_admet_predictions | molecule_table@1 | 1 | 8c801a36-ea3a-46bf-a3a5-837f2b87a5e0 | table_file: c8035b1c508ae8e62993e2fa139d817500059e8f7f10d1f5f7ee98b5090899f5; metadata_json: 2f8ad06c639a444b765a2e867e8e8cb7c0fffbdf5c6aba171a0855a42d1580f7 |

## 4. 科学元数据核对

| 字段 | 预期 | 实际 |
| --- | --- | --- |
| model_name | MolP-PC | MolP-PC |
| model_version | 0.1.1 | 0.1.1 |
| endpoint_ref | 与 Tool Package 声明一致 | local_runtime:molp-pc-property-prediction@0.1.1 |
| runtime_ref | 与 Tool Package 声明一致 | container:registry.example/sciminer/molp-pc-runtime:0.1.1@sha256:4444444444444444444444444444444444444444444444444444444444444444 |
| weights_ref | 与 Tool Package 声明一致 | artifacts://model-weights/molp-pc-property-prediction/0.1.1/weights.json#sha256:6666666666666666666666666666666666666666666666666666666666666666 |
| evidence_level | engineering_smoke_only | engineering_smoke_only |
| applicability_domain_status | unknown 或模型实际输出 | unknown |

## 5. 结论

| 字段 | 记录值 |
| --- | --- |
| 验收结论 | 自动检查通过 |
| 阻断问题 | 如无则填 N/A |
