# K8s / Slurm Executor Adapter 设计

## 1. 目标

分子对接、MD、深度学习分子生成、大规模 ADMET 和虚拟筛选都可能需要远超 Web 服务本机能力的计算资源。平台需要一个小而稳定的 Executor Adapter Interface，让任务系统可以用同一套方式提交、查询、取消、收集日志和回收结果，而不用关心底层是 Docker、SSH、K8s、Slurm 还是 Remote API。

该设计的核心是深模块：调用方只学习一个小 Interface，复杂的集群差异留在 Adapter 实现内部。

## 2. 模块定位

```text
Task Scheduler
  │
  ▼
Execution Request Builder
  │
  ▼
Executor Adapter Interface
  │
  ├─ Docker Adapter
  ├─ SSH Adapter
  ├─ K8s Job Adapter
  ├─ Slurm Adapter
  └─ Remote API Adapter
```

职责分离：

- Binding Resolver 负责准备输入绑定。
- Request Builder 负责生成标准运行请求。
- Executor Adapter 负责和执行环境交互。
- Artifact Persistence 负责把输出变成标准 Artifact。

## 3. Executor Adapter Interface

建议 Interface：

```ts
interface ExecutorAdapter {
  submit(request: TaskExecutionRequest): Promise<SubmittedExecution>
  inspect(handle: ExecutionHandle): Promise<ExecutionStatus>
  cancel(handle: ExecutionHandle): Promise<CancelResult>
  logs(handle: ExecutionHandle, cursor?: string): Promise<ExecutionLogs>
  collect(handle: ExecutionHandle): Promise<CollectedOutputs>
}
```

设计约束：

- Interface 不暴露 K8s Pod、Slurm JobId 或 SSH 命令细节。
- `ExecutionHandle` 可以保存 Adapter 私有元数据，但调用方只把它当 opaque handle。
- `collect()` 只返回平台可识别的输出清单，不直接持久化 Artifact。
- `cancel()` 必须幂等；已完成或已取消的任务再次取消应返回稳定结果。

## 4. 标准运行请求

```yaml
task_id: <uuid>
tool_slug: molecular-docking
run_context:
  project_id: <uuid-or-null>
resource_profile:
  tier: cpu-medium
  cpu: 8
  memory_gb: 16
  gpu_required: false
  expected_minutes: 30
  timeout_minutes: 120
inputs:
  workdir: /work/<task_id>
  parameters_file: request.json
  artifact_files:
    receptor:
      receptor_pdbqt: inputs/receptor.pdbqt
    ligand:
      structure_3d_sdf: inputs/ligand.sdf
outputs:
  manifest_path: outputs/result.manifest.json
  output_dir: outputs/
runtime:
  image: <image-ref-or-null>
  command: ["run-tool"]
  env: {}
```

请求应由后端统一构造，前端不应拼接命令、路径或集群参数。

## 5. 状态模型

平台任务状态与执行环境状态映射：

| 平台状态 | K8s 示例 | Slurm 示例 | 说明 |
| --- | --- | --- | --- |
| queued | Job created / Pod pending | PENDING | 已提交但未运行 |
| running | Pod running | RUNNING | 正在计算 |
| succeeded | Job complete | COMPLETED | 输出可收集 |
| failed | Pod failed | FAILED / TIMEOUT / NODE_FAIL | 执行失败 |
| cancelled | Job deleted | CANCELLED | 用户或系统取消 |
| unknown | API unavailable | controller unavailable | 需要重试查询 |

Adapter 必须把底层状态压缩为平台状态，并保留原始状态用于诊断。

## 6. 输入输出 Staging 协议

### 6.1 输入 staging

每个任务有独立工作目录：

```text
work/<task_id>/
  request.json
  inputs/
  outputs/
  logs/
```

输入来源：

- 对象存储下载到执行环境。
- 共享文件系统软链接或复制。
- Remote API 使用预签名 URL 或平台文件转发。

原则：

- 工作目录只属于一个任务。
- 输入文件保持只读。
- 文件名可读但不作为业务语义来源，语义来自 request manifest。

### 6.2 输出 collection

工具必须产出结果 manifest：

```json
{
  "status": "succeeded",
  "outputs": {
    "scores": {
      "type": "docking_score_table@1",
      "files": {
        "table_file": "outputs/scores.csv",
        "metadata_json": "outputs/scores.metadata.json"
      }
    }
  },
  "metrics": {
    "runtime_seconds": 1830
  }
}
```

Adapter 只收集 manifest 和文件；标准 Artifact 校验由后端 Artifact Persistence 完成。

## 7. Resource Profile 映射

### 7.1 K8s 映射

| Resource Profile | K8s 字段 |
| --- | --- |
| `cpu` | `resources.requests.cpu` / `limits.cpu` |
| `memory_gb` | `resources.requests.memory` / `limits.memory` |
| `gpu_required` | `nvidia.com/gpu` request |
| `gpu_memory_gb` | node label / device class |
| `timeout_minutes` | `activeDeadlineSeconds` |
| `tier` | queue namespace / priority class / node selector |

### 7.2 Slurm 映射

| Resource Profile | Slurm 参数 |
| --- | --- |
| `cpu` | `--cpus-per-task` |
| `memory_gb` | `--mem` |
| `gpu_required` | `--gres=gpu:<n>` |
| `timeout_minutes` | `--time` |
| `tier` | `--partition` / `--qos` |
| `parallelism` | array job 或多任务策略 |

## 8. K8s Job Adapter

### 8.1 提交

提交时创建 Job：

- 注入 task_id、tool_slug、user_id 标签。
- 挂载对象存储凭据或使用 sidecar 拉取输入。
- 设置资源、超时、重启策略。
- 写入 ExecutionHandle：namespace、job_name、pod_selector。

### 8.2 查询

查询时读取 Job 和 Pod 状态：

- Job complete -> succeeded。
- Pod failed 且无可重试 -> failed。
- Pending 超过阈值 -> queued with reason。

### 8.3 取消

取消时删除 Job 或设置终止标记。删除必须带 propagation policy，避免孤立 Pod。

### 8.4 日志

日志来自 Pod logs。多容器时优先工具主容器；sidecar 日志作为诊断附件。

## 9. Slurm Adapter

### 9.1 提交

提交时生成 sbatch 脚本：

```bash
#!/usr/bin/env bash
#SBATCH --job-name=sciminer-<task_id>
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=logs/slurm-%j.out
#SBATCH --error=logs/slurm-%j.err

set -euo pipefail
run-tool --request request.json
```

Adapter 保存 Slurm JobId 到 ExecutionHandle。

### 9.2 查询

优先使用 `squeue` 查询运行中任务，使用 `sacct` 查询历史结果。状态映射必须覆盖 COMPLETED、FAILED、CANCELLED、TIMEOUT、OUT_OF_MEMORY、NODE_FAIL。

### 9.3 取消

调用 `scancel <job_id>`。如果任务已经结束，返回幂等取消结果。

### 9.4 日志

从共享文件系统或对象存储读取 stdout/stderr，按 cursor 增量返回。

## 10. SSH Adapter 与集群 Adapter 的关系

SSH Job 是过渡 Adapter，也可以作为 Slurm 登录节点的 transport。建议拆成两层：

```text
SSH Transport
  ├─ Raw SSH Command Adapter
  └─ Slurm Adapter over SSH
```

这样可以复用 SSH 连接、上传、下载、日志和安全配置，同时避免 Slurm 逻辑散落在普通 SSH Job 中。

## 11. 错误模型

统一错误类型：

| 错误 | 含义 | 用户提示 |
| --- | --- | --- |
| `staging_failed` | 输入准备失败 | 输入文件准备失败，请检查上传或上游产物 |
| `submit_failed` | 提交到执行环境失败 | 任务未能提交到计算资源 |
| `capacity_unavailable` | 资源暂不可用 | 当前队列资源不足，可稍后重试 |
| `runtime_failed` | 工具进程失败 | 工具运行失败，请查看日志 |
| `timeout` | 超时 | 任务超过超时时间被终止 |
| `cancel_failed` | 取消失败 | 取消请求未成功，系统将继续同步状态 |
| `collect_failed` | 输出回收失败 | 任务完成但结果回收失败 |

错误 detail 应保留底层状态、退出码和关键日志片段，但前端默认展示研发人员可理解的摘要。

## 12. 安全边界

- 用户不能直接提交任意 shell 命令。
- 工具契约不保存明文集群凭据。
- Kubeconfig、SSH key、Slurm 登录配置由平台安全配置管理。
- Remote API 服务应部署在可信网络，第一版可不做用户级认证，但平台仍要记录服务来源和管理员审核。
- 所有输出文件必须经过平台持久化和权限控制后才能下载。

## 13. 测试矩阵

| 场景 | 期望 |
| --- | --- |
| K8s 提交成功 | Task 获得 ExecutionHandle，状态 queued/running |
| K8s Job 完成 | collect 后生成 TaskOutput 和标准 Artifact |
| K8s 删除 Job | Task 进入 cancelled |
| Slurm sbatch 成功 | 记录 JobId 并可查询状态 |
| Slurm TIMEOUT | Task failed，错误类型 timeout |
| 日志增量读取 | cursor 后只返回新增日志 |
| 输出 manifest 缺 required role | Artifact 校验失败，Task 给出 collect_failed |
| Adapter API 短暂不可用 | 状态 unknown，调度器重试，不误判失败 |

## 14. 演进路线

1. 抽出标准 Executor Adapter Interface 和 TaskExecutionRequest。
2. 用现有 SSH Job 对齐 Interface，补齐 cancel、logs、collect。
3. Docker Executor 使用同一 request/output manifest。
4. 实现 K8s Job Adapter。
5. 实现 Slurm Adapter over SSH。
6. 将对接、MD、批量 ADMET 迁移到集群 Adapter。

## 15. 禁止事项

- 禁止前端构造集群命令。
- 禁止工具直接写平台数据库。
- 禁止 Adapter 持久化标准 Artifact。
- 禁止每个工具各自实现日志、取消和输出回收。
- 禁止把 Slurm/K8s 字段泄漏到普通 TaskCreate payload。
