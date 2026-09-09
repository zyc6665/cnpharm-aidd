# AT-003 平台工具调用真实运行记录

> 本记录来自平台 API。不得记录 `model/MolP-PC/platform_run.sh` 作为 AT-003 平台验收结果。

## 1. 平台任务记录

| 字段 | 记录值 |
| --- | --- |
| 项目 ID | 66c0bd5b-b506-4aa2-b4b0-52fa5ffaad6a |
| 工具 slug | molp-pc-property-prediction |
| ToolVersion | 0.1.1 |
| tool_version_id | d7600055-5c80-4992-8763-c7a43a346762 |
| task_id | 9322c6b7-0e1f-4ffc-8cfd-01f57269bee9 |
| 调度模式 | direct |
| 调度队列 | N/A |
| 标准输入绑定 | molecules -> bb92b727-ee85-4fa5-b7f5-f15c171d1514 |
| 任务状态 | success |

## 2. 输入与输出哈希

| 字段 | 记录值 |
| --- | --- |
| input_sha256 | artifacts__ligands__ligand_001 SMILES table table_file: 092871959942a5b636410725ccfe0a0f41f920bd71ccc7171ae718dc8fcb3da4; artifacts__ligands__ligand_001 SMILES table metadata_json: 34cbf1b8a478a40408aa4215d525930cddccedeab37ba8fe19c848231d1e146c |
| output_sha256 | logs__run.log: a43f0431f7b4715aea662aac7dd776c6024dd86356fc6f3b6f0a4df3f97d96b2; artifacts__cb_data_result.csv: c8035b1c508ae8e62993e2fa139d817500059e8f7f10d1f5f7ee98b5090899f5; artifacts__properties__metadata.json: 781875357f255cb46c53c2af32405e248de29cfafefaa3b87d389afe0eed380c; reports__report.json: fc0af618ff0655d7bd0814e06c5861743df170a93ab2ed473754c4aa917d3758 |

## 3. 输出 Artifact 记录

| 输出 | 标准类型 | ArtifactVersion | artifact_version_id | 文件 role / checksum |
| --- | --- | --- | --- | --- |
| 9322c6b7-0e1f-4ffc-8cfd-01f57269bee9_molp_pc_adapter_report | run_report@1 | 1 | 7dc8baef-5230-43a0-baac-04ace8e24800 | report_json: fc0af618ff0655d7bd0814e06c5861743df170a93ab2ed473754c4aa917d3758 |
| 9322c6b7-0e1f-4ffc-8cfd-01f57269bee9_molp_pc_admet_predictions | molecule_table@1 | 1 | adf5e2b4-bf18-4617-9ab5-ee9d46c810a3 | table_file: c8035b1c508ae8e62993e2fa139d817500059e8f7f10d1f5f7ee98b5090899f5; metadata_json: 781875357f255cb46c53c2af32405e248de29cfafefaa3b87d389afe0eed380c |

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
