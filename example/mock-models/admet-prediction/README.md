# ADMET Mock Prediction

> **本包为演示用 mock，数值不可用于科研决策。** 详见 `docs/model-card.md`。

## 这是什么

`admet-prediction` 是一个符合 `aidd.sciminer/tool-package` 契约的 **mock 模型包**，用于在真实模型资产到位前
解耦前端 P-15~P-28 页面与平台联调。mock 版与真实版同构：真模型到位后只替换镜像 tag 与 manifest，
前端与平台零改动。

## mock 如何被识别（重要）

平台的 `ToolPackageMetadata` 采用 `extra="forbid"`，但本仓库已为该模型新增显式字段 `mock: bool`
（默认 `False`）。因此本包在 `tool.yaml` 的 `metadata.mock` 中声明：

```yaml
metadata:
  slug: admet-prediction
  version: 0.1.0
  mock: true
```

识别链路：

1. 建任务时 `backend/app/tasks/service.py` 读取 `tool_version.config["tool_package_manifest"]`，
   若其 `metadata.mock` 为真，则写入 `task.extra_data["mock"] = True`。
2. `GET /api/v1/tasks/{task_id}`、`GET /api/v1/results/{task_id}`、
   `GET /api/v1/projects/{project_id}/results` 的响应体都带 `mock: bool`。
3. 写入产物时 `backend/app/services/standard_artifacts.py` 在 `manifest_json` 中写 `"mock": true`。

## 目录结构

```
tool.yaml                 # v2 manifest（api_version / artifacts / parameters_schema / runtime / variants）
schemas/parameters.schema.json
variants/mock-local.yaml  # cli 执行器，本机零镜像依赖
variants/haiguang-dcu.yaml # container 占位（海光 DCU）
runner/mock_runner.py     # 真正可执行的 Python 脚本（RDKit 真算 + 确定性合成值）
examples/request.json     # 标准 request.v1 示例
docs/model-card.md
tests/test_admet_prediction_contract.py
```

## 运行

平台通过环境变量调用 `runner/mock_runner.py`：

```bash
export DRP_TASK_FILE=/path/to/task.json
export DRP_OUT_DIR=/path/to/output
export DRP_RESULT_FILE=/path/to/output/result.json
python runner/mock_runner.py
```

也可以 `from runner.mock_runner import run; run(task, out_dir)` 离线调用。

## 与冻结契约的偏差（受后端 schema 约束，非契约变更）

- `variants.executor_types` 只接受 `container / cli / remote_job`，因此 `mock-local` 用 `cli`、
  `haiguang-dcu` 用 `container`（不是契约文字里的 `python_script / docker_image`）。
- `runtime.executor_support` 只接受 `ssh_docker_exec / slurm / k8s_job`，因此声明
  `[ssh_docker_exec, slurm, k8s_job]`（不是契约文字里的 `[docker_image, python_script]`）。
- `haiguang-dcu` 变体未做真机验证，按 `validator.py` 规则必须使用
  `adapted_pending_hardware_validation`（而不是 `unvalidated`）。

以上偏差均为后端 schema 硬约束导致，已由后端 schema 校验器确认。
