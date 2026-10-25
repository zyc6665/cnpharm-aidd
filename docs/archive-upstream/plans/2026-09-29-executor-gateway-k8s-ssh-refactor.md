# Executor Gateway K8s/SSH Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement the plan task-by-task.

**Goal:** 将工具任务执行统一到可测试的 Executor Gateway，支持 K8s Job 主路径和 SSH Job 过渡路径，同时保留旧执行器的兼容边界。

**Architecture:** 扩展 `backend/app/execution` 作为稳定的应用执行边界。K8s 与 SSH 适配器都只依赖 transport/secret provider 协议，真实 Kubernetes/SSH 客户端由基础设施层注入；TaskExecutor 通过 resolver 识别新的 `k8s_job` 类型，旧 Docker/Python/Remote API 继续走兼容 resolver。执行记录只保存 adapter 类型、外部句柄和脱敏请求快照。

**Tech Stack:** Python 3.13、Pydantic、SQLAlchemy、pytest/pytest-asyncio、现有 FastAPI/Celery 任务执行链路。

---

### Task 1: 冻结执行契约与失败行为

**Files:**
- Modify: `backend/app/execution/contracts.py`
- Modify: `backend/app/execution/port.py`
- Modify: `backend/app/execution/service.py`
- Test: `test/test_execution_port.py`

**Steps:**
1. 增加 `k8s_job`、`ssh_job` 的规范化执行类型，同时保留 `ssh`、`remote_job` 等历史值可解析。
2. 为 Gateway 增加 `inspect`/`reconcile` 语义，保留现有 `status` 调用兼容。
3. 添加未知类型和取消幂等的失败行为测试。
4. 运行 `python -m pytest test/test_execution_port.py -q`，确认先出现预期失败。
5. 实现最小契约变更并重新运行该测试文件。

### Task 2: 实现 K8s Job Adapter

**Files:**
- Create: `backend/app/execution/adapters/kubernetes.py`
- Modify: `backend/app/execution/adapters/__init__.py`
- Test: `test/test_kubernetes_execution_adapter.py`

**Steps:**
1. 先写 K8s 配置校验、SecretProvider、Transport 生命周期和日志脱敏测试。
2. 实现 `KubernetesJobExecutionConfig`、`KubernetesSecretProvider`、`KubernetesJobTransport` 协议和 `KubernetesJobExecutionAdapter`。
3. 适配器只负责提交、状态、reconcile、日志、取消、产物收集；不在业务层引入 kubernetes SDK。
4. 运行定向测试并修复协议/状态映射问题。

### Task 3: 统一工具类型到执行 Gateway

**Files:**
- Modify: `backend/app/execution/executor_types.py`
- Modify: `backend/app/execution/records.py`
- Modify: `backend/app/tasks/executors/resolver.py`
- Test: `test/test_execution_executor_types.py`
- Test: `test/test_executor_module_layout.py`

**Steps:**
1. 为 `k8s_job` 增加 canonical adapter 映射，并保留旧 `remote_job` 记录读取兼容。
2. 让 resolver 识别 `k8s_job`，通过独立 Gateway-backed executor 边界处理，不改变旧 executor 的默认行为。
3. 对新的 ToolVersion 类型增加明确的缺少适配器错误，而不是静默回退到 Docker/Python。
4. 运行执行器类型和模块布局测试。

### Task 4: 接入任务执行生命周期的执行句柄

**Files:**
- Modify: `backend/app/execution/records.py`
- Modify: `backend/app/worker/tasks.py`
- Modify: `backend/app/tasks/cancellation.py`
- Test: `test/test_execution_records.py`
- Test: `test/test_task_direct_execution.py`

**Steps:**
1. 让新 Gateway 执行路径在提交后持久化外部 Job ID，并在 reconcile/取消时复用同一个句柄。
2. 取消路径按 `k8s_job` 使用 Job 删除/终止语义，SSH 继续使用现有远程取消逻辑。
3. 确保旧 attempt 未确认终止前不会释放资源租约或接受新 attempt 结果。
4. 运行执行记录、取消和任务执行定向测试。

### Task 5: 回归与文档同步

**Files:**
- Modify: `docs/architecture/19-执行环境与资源调度重构方案.md`
- Modify: `docs/architecture/09-K8s-Slurm-Executor-Adapter设计.md`
- Test: `test/test_execution_port.py`
- Test: `test/test_kubernetes_execution_adapter.py`
- Test: `test/test_execution_records.py`

**Steps:**
1. 更新适配器注入方式、状态 reconcile 和当前未接真实集群的边界。
2. 运行定向测试、`python -m compileall -q backend/app` 和 `git diff --check`。
3. 检查工作区差异，确认没有修改无关的历史实现或提交 git。
