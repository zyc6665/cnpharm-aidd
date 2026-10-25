# V1 P0 交付前完整回归记录

| 项目 | 内容 |
| --- | --- |
| 执行时间 | 2026-09-09T07:06:35Z |
| 分支 | `v1.0-7.28` |
| HEAD | `3124c9e` |
| 后端健康 | `{"status":"healthy","version":"1.0.0"}` |
| 结论 | 通过 |

## 回归范围

- V1 地基：Run Preparation、Standard Artifact、Result Manifest、Task Command、Executor Gateway、Workflow Hydration。
- Artifact 面：类型、标准类型、来源任务、role、模型名称、交付元数据检索，以及下载权限与审计。
- 基础 ADMET：MolP-PC Tool Package v2、模型包 runtime contract、AT-003 前端流程入口。
- 前端交付面：Artifact API、项目总览 Artifact 常用筛选、工作流预设、任务详情输出摘要、Artifact renderer。

## 执行命令

### 后端 P0 回归

```bash
python -m pytest "test/test_run_preparation.py" \
  "test/test_standard_artifact_service.py" \
  "test/test_standard_result_parser.py" \
  "test/test_task_detail_visualization.py" \
  "test/test_admin_system_routes.py" \
  "test/test_worker_standard_artifact_outputs.py" \
  "test/test_workflow_validation_standard_artifacts.py" \
  "test/test_workflow_scheduler.py" \
  "test/test_typed_artifacts_api.py" \
  "test/test_file_artifacts_api.py" \
  "test/test_molp_pc_tool_package_v2.py" \
  "model/MolP-PC/tests/test_molp_pc_runtime_contract.py" -q
```

结果：`87 passed in 32.35s`

### 前端 P0 回归

```bash
npm --prefix "frontend" test -- \
  "src/api/artifacts.spec.ts" \
  "src/views/projects/Overview.spec.ts" \
  "test/workflow-canvas-presets.test.ts" \
  "src/composables/useWorkflowCanvas.spec.ts" \
  "src/domain/tasks/detail.spec.ts" \
  "src/domain/tasks/output-summary.spec.ts" \
  "src/components/tasks/TaskOutputSummary.spec.ts" \
  "src/components/artifacts/ArtifactRenderer.spec.ts"
```

结果：`8 passed` test files，`42 passed` tests。

### AT-003 浏览器 smoke

```bash
npm --prefix "frontend" exec -- playwright test \
  --config "frontend/playwright.config.ts" \
  "e2e/at003-workflow-preset.spec.ts" \
  --project=chromium
```

结果：`1 passed`。

### 前端类型检查

```bash
cd "frontend" && npm exec -- vue-tsc -b
```

结果：exit code `0`。

## 限制说明

- 本记录是工程交付 P0 回归，不替代 MolP-PC 科学外部基准验证。
- AT-003 平台真实运行证据仍以 `docs/verification/at003-platform-run-2026-09-09.md` 为准。
- K8s/Slurm 生产化、MD 完整生产链路、复杂 Agent 自动执行和多轮实验闭环仍不属于 V1 P0 阻断项。
