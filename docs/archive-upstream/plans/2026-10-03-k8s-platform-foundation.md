# K8s Platform Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement the plan task-by-task.

**Goal:** 在镜像和 MinIO 尚未就绪时，先冻结平台侧 Kubernetes 执行契约，并让已发布 Tool Package 能被明确绑定为 `k8s_job` 工具版本。

**Architecture:** Tool Package 只声明不可变镜像、入口和执行能力；管理员绑定批准的 Resource Profile；Execution Gateway 将统一 `ExecutionRequest` 渲染为受控 Kubernetes Job manifest。集群 namespace、ServiceAccount、凭据和镜像拉取 Secret 由 worker 执行环境配置，不进入工具注册数据。

**Tech Stack:** Python 3.13、Pydantic、pytest、现有 FastAPI/Celery、Kubernetes 原生 Job manifest（本阶段不引入 Kubernetes SDK）。

---

### Task 1: 冻结 K8s Job manifest 渲染契约

**Files:**
- Create: `backend/app/execution/adapters/kubernetes_manifest.py`
- Modify: `backend/app/execution/adapters/kubernetes.py`
- Test: `test/test_kubernetes_job_manifest.py`

**Scope:** 将执行请求中的 immutable image、entrypoint、资源快照、任务标签和执行环境配置转换为最小 Kubernetes Job manifest；禁止 mutable image、任意节点字段和平台凭据进入工具请求。

### Task 2: 冻结 Tool Package 的 K8s 注册绑定

**Files:**
- Create: `backend/app/tool_packages/kubernetes_binding.py`
- Test: `test/test_kubernetes_tool_binding.py`

**Scope:** 仅允许声明 `runtime.executor_support` 包含 `k8s_job` 且主运行时为带 digest 的 container 的 V2 包；管理员显式选择 variant 和已登记 Resource Profile，生成不包含集群凭据的 `tool_config`。

### Task 3: 增加执行环境配置门禁

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Test: `test/test_config_security.py`

**Scope:** 开启 K8s executor 时，必须提供 cluster alias、namespace、credential reference 和 ServiceAccount；默认保持关闭，避免 MinIO/镜像未就绪时误启用计算路径。

### Task 4: 接入真实 transport 前的验收

**Files:**
- Create: `backend/app/execution/transports/kubernetes_http.py`
- Create: `backend/app/execution/transports/kubernetes_runtime.py`
- Create: `backend/app/execution/transports/__init__.py`
- Modify: `backend/app/execution/adapters/kubernetes.py`
- Modify: `backend/app/worker/celery_app.py`
- Test: `test/test_kubernetes_http_transport.py`
- Test: `test/test_kubernetes_runtime.py`

**Scope:** 使用 `httpx` 接入 Kubernetes REST API，完成 Job 创建、409 幂等、状态、日志和取消；worker 仅从 Pod ServiceAccount 文件读取 token/CA，并在进程级注册 Gateway。对象存储 artifact collector 使用固定的 `executions/<namespace>/<job-name>` 前缀下载 `result.json` 和输出文件，校验 result.v2、相对路径和 SHA-256 后再交给平台 File/Artifact 持久化；未配置 MinIO 时明确失败，不伪造产物回收成功。

### Task 5: 建立开发部署基线

**Files:**
- Create: `deploy/kubernetes/namespace.yaml`
- Create: `deploy/kubernetes/execution-rbac.yaml`
- Create: `deploy/kubernetes/minio-dev.yaml`
- Create: `deploy/kubernetes/minio-dev-nodeport.yaml`
- Create: `deploy/kubernetes/kustomization.yaml`
- Create: `deploy/kubernetes/smoke-image/Dockerfile`
- Create: `deploy/kubernetes/smoke-image/run-smoke.sh`
- Create: `deploy/kubernetes/README.md`
- Test: `test/test_kubernetes_deployment_baseline.py`

**Scope:** 生成可审查的开发资源模板，不写入凭据、不自动 apply、不伪造镜像 digest；MinIO 使用现有 Compose 中的开发版本，生产前仍需替换为经批准的镜像 digest 和高可用存储方案。

### Task 6: 接通对象存储结果回收契约

**Files:**
- Create: `backend/app/execution/transports/kubernetes_artifacts.py`
- Modify: `backend/app/execution/transports/kubernetes_http.py`
- Modify: `backend/app/execution/transports/kubernetes_runtime.py`
- Modify: `backend/app/tasks/executors/kubernetes_job.py`
- Modify: `backend/app/services/execution_artifacts.py`
- Test: `test/test_kubernetes_artifacts.py`

**Scope:** Job 只通过平台注入的对象存储环境变量上传结果；Worker 负责下载、校验、临时落盘、创建 File 记录并复用现有标准 Artifact 持久化。真实 K8s executor 仍需完成 client Secret、bucket policy、镜像构建推送和端到端 smoke 验收后才能开启。

### Task 7: 接通 K8s 输入 staging 和 smoke uploader

**Files:**
- Create: `backend/app/services/kubernetes_input_staging.py`
- Create: `deploy/kubernetes/smoke-image/run-smoke.py`
- Modify: `backend/app/tasks/executors/kubernetes_job.py`
- Modify: `deploy/kubernetes/smoke-image/Dockerfile`
- Modify: `deploy/kubernetes/smoke-image/run-smoke.sh`
- Test: `test/test_kubernetes_input_staging.py`

**Scope:** Worker 先校验并上传任务 File 输入到 `inputs/<task-id>/<attempt-id>/...`，Job 通过 `SCIMINER_INPUTS_JSON` 获取不可变对象 URI；smoke image 使用 MinIO SDK 下载输入、验证 checksum，并按“输出文件先上传、`result.json` 最后上传”的顺序完成结果提交。当前尚未 apply client Secret、创建 bucket policy 或构建推送镜像。
