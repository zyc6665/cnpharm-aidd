# 管理员 K8s 工具注册实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 管理员可从已发布 Tool Package 创建不影响当前 SSH 版本的 K8s 候选 ToolVersion，并在真实 smoke 成功后显式提升。

**Architecture:** ToolPackageVersion 是模型来源；ToolVersion 是不可变的运行绑定。后端以数据库中的 manifest 为唯一权威来源，构造 digest 固定的 K8s 配置；候选版本保持 inactive，管理员 smoke 和 promotion 使用受控 API。无需新增模型表，smoke 审计复用 Task 与服务端 `extra_data` 标记。

**Tech Stack:** FastAPI、SQLAlchemy AsyncSession、Pydantic、Vue 3、Vitest、pytest。

---

## 执行约束

- 不改动或覆盖 SSH 当前 ToolVersion；注册必须保持 `Tool.current_version_id` 不变。
- 不提交或推送 Git，不创建分支；按主人当前指示只做工作区改动。
- 不在本计划内构建镜像或执行集群部署。端到端 smoke 需要可用的 K8s Worker、MinIO 和节点可拉取的模型镜像。
- 当前 `ToolVersion` 无独立 smoke 状态字段；以任务 `tool_version_id` 和服务端写入的 `extra_data.run_kind=tool_version_smoke` 作为审计依据。若后续需要高频查询，再评估专用状态模型。
- 版本资源快照必须优先使用 ToolVersion 的已登记 Resource Profile；Tool 级 GPU 字段是跨版本共享值，不能覆盖 K8s 候选版本的资源要求。

### Task 1: 覆盖 K8s 绑定输入边界

**Files:**
- Modify: `test/test_kubernetes_tool_binding.py`
- Modify: `backend/app/tool_packages/kubernetes_binding.py`

**Step 1: 补充失败测试**

覆盖未声明 `k8s_job`、variant 不存在、未登记 Resource Profile、非 container 主 artifact、缺失/格式错误 digest，以及已含 `@` 的镜像引用仍只生成一个 digest suffix。

**Step 2: 运行绑定测试确认失败**

Run: `pytest -q test/test_kubernetes_tool_binding.py`

Expected: 新增边界测试至少一项失败，测试进程成功启动。

**Step 3: 实现最小修复**

保持绑定 helper 纯函数职责，只校验 manifest 和平台资源档位并返回 K8s 运行字段；包数据库查询和 ToolVersion 写入留给后续注册服务。

**Step 4: 重跑绑定测试**

Run: `pytest -q test/test_kubernetes_tool_binding.py`

Expected: 全部通过。

### Task 2: 实现服务端权威注册 API

**Files:**
- Modify: `backend/app/schemas/tool_packages.py`
- Modify: `backend/app/api/v1/tool_packages.py`
- Create: `backend/app/tool_packages/kubernetes_registration.py`
- Test: `test/test_tool_package_api.py`

**Step 1: 写 API 失败测试**

覆盖管理员成功注册、普通用户拒绝、未发布包拒绝、错误包版本归属拒绝、manifest 无效/无签名字段拒绝、无 K8s executor/无 digest/未知 variant/未登记 profile 拒绝、版本冲突拒绝、无现有 Tool 时缺少分类拒绝。

**Step 2: 运行 API 测试确认失败**

Run: `pytest -q test/test_tool_package_api.py`

Expected: 新注册接口相关测试因路由或服务未实现而失败。

**Step 3: 添加请求 schema 与注册服务**

请求接收 `package_version_id`、`target_tool_id`、新 Tool 所需的 `category_id`、ToolVersion 版本号、`variant_name` 和 `resource_profile`。服务从数据库读取 manifest，不接收客户端 manifest；重验包版本归属、发布状态、manifest 和绑定条件。目标 Tool 必须与 package slug 一致；创建新 Tool 时设为 DRAFT。

将包 manifest 快照及 `{package_id, package_version_id, manifest_digest}` 来源信息保存到 ToolVersion config；ToolVersion 设 `is_active=False`。创建 Tool（如需）、ToolVersion 在同一事务完成，既有当前版本指针不改变。

**Step 4: 实现管理员资源选项读取**

增加管理员选项 API，从当前已发布包版本返回可用 variant、Resource Profile ID 与同 slug Tool 摘要。Profile 仅从 `RESOURCE_PROFILE_REGISTRY_JSON` 派生；注册接口仍独立复验。

**Step 5: 运行 API 测试确认通过**

Run: `pytest -q test/test_tool_package_api.py test/test_kubernetes_tool_binding.py`

Expected: 注册和 helper 测试全部通过；既有发布行为不回归。

### Task 3: 限制普通任务版本选择并增加管理员 smoke

**Files:**
- Modify: `backend/app/tasks/service.py`
- Modify: `backend/app/tasks/resource_profile.py` only if profile precedence belongs in the normalization helper
- Modify: `backend/app/api/v1/tool_versions.py`
- Modify: `backend/app/schemas/tasks.py` only if a dedicated smoke request schema is needed
- Test: `test/test_task_direct_execution.py`

**Step 1: 写版本隔离失败测试**

覆盖跨 Tool 的 version ID、inactive/deprecated 候选经普通任务入口运行均被拒绝；当前 SSH 版本照常运行。覆盖当 Tool 级 GPU 字段与 K8s Resource Profile 不同时，任务资源快照仍按该 ToolVersion 档位生成。覆盖管理员 smoke 能针对 inactive K8s 候选创建任务，且任务版本 ID 和服务端 smoke 标记正确。

**Step 2: 运行直接任务测试确认失败**

Run: `pytest -q test/test_task_direct_execution.py`

Expected: 新增用例先因现有版本选择缺少校验或 smoke 路由不存在而失败。

**Step 3: 加固共享版本解析**

普通任务解析版本时校验 `ToolVersion.tool_id == Tool.id`、未废弃且允许执行；不因客户端提供 ID 而绕过状态。构造资源快照时，对已登记的 ToolVersion Resource Profile 不传入共享 Tool 级 GPU 覆盖值。管理员 smoke 通过服务端内部参数允许指定 inactive 候选，不向普通任务请求暴露此绕过开关。

**Step 4: 增加管理员 smoke 路由**

复用现有 direct/Celery 调度服务，使用版本指定的 K8s 配置；从请求接收模型所需的参数、文件和 Artifact 绑定。仅在服务端为任务写入 `extra_data.run_kind=tool_version_smoke`，保留 Task 作为审计记录。

**Step 5: 重跑直接任务测试**

Run: `pytest -q test/test_task_direct_execution.py`

Expected: 当前 SSH 路径、标准输入绑定和候选版本权限测试全部通过。

### Task 4: 增加 smoke 门禁 promotion

**Files:**
- Modify: `backend/app/api/v1/tool_versions.py`
- Modify: `backend/app/tools/version_manager.py` only if needed for atomic activation/current-pointer update
- Test: `test/test_task_direct_execution.py` or a focused new `test/test_tool_version_promotion_api.py`

**Step 1: 写 promotion 失败测试**

覆盖无 smoke、失败或非最新成功 smoke、不同 Tool 的 smoke、被废弃版本均不能提升；最新 smoke 成功后候选成为 active/current，旧 SSH 版本仍保留且可回切。

**Step 2: 运行 promotion 测试确认失败**

Run: `pytest -q test/test_tool_version_promotion_api.py`

Expected: 若新增独立测试文件，测试先因接口不存在失败。

**Step 3: 实现管理员 promotion**

增加版本 promotion API，校验目标版本属于 Tool 且未废弃；inactive K8s 候选须以同 Tool、同版本的最新 smoke 状态为准并要求 SUCCESS，已 active 版本可直接用于回滚。扩展 `ToolVersionManager`，在一次提交内完成候选激活与当前指针切换，提交后复用缓存清理逻辑；不要分两次提交激活和切换，避免部分状态落库。

**Step 4: 重跑 promotion 测试**

Run: `pytest -q test/test_tool_version_promotion_api.py test/test_task_direct_execution.py`

Expected: promotion 门禁和 SSH 保持/回切测试通过。

### Task 5: 增加管理员 K8s 注册向导

**Files:**
- Modify: `frontend/src/api/tool-packages.ts`
- Modify: `frontend/src/types/tool-packages.ts`
- Modify: `frontend/src/views/admin/ToolPackages.vue`
- Create: `frontend/src/domain/tool-packages/kubernetes-registration.ts`
- Test: `frontend/src/domain/tool-packages/kubernetes-registration.spec.ts`

**Step 1: 写前端纯函数失败测试**

覆盖从已发布包筛选可注册 K8s variant、构造默认 ToolVersion 标签、显示现存同 slug Tool，以及不支持 K8s 或缺少 digest 时禁止提交。

**Step 2: 运行前端测试确认失败**

Run: `npm test -- src/domain/tool-packages/kubernetes-registration.spec.ts`

Expected: 新模块或行为缺失导致失败。

**Step 3: 添加 API 类型与请求方法**

为 options、registration、smoke 和 promotion 响应建立窄类型；前端提交选择项而非 manifest。不要把 registry 凭据、Kubernetes Secret 或任意 Pod 字段放入请求。

**Step 4: 添加注册/候选操作界面**

从 Tool Package 详情进入 K8s 注册表单；展示 digest、variant、entrypoint 摘要和已批准 profile。若 slug 对应现有 Tool，默认提供“新增候选版本”选择且说明 SSH 当前版本不变；若新建 Tool，要求分类。候选详情展示 smoke 状态，只在成功后允许 promotion。

**Step 5: 运行前端测试与构建**

Run: `npm test -- src/domain/tool-packages/kubernetes-registration.spec.ts`

Expected: 新增逻辑测试通过。

Run: `npm run build`

Expected: `vue-tsc` 与 Vite build 成功。

### Task 6: 更新使用说明并做回归验证

**Files:**
- Modify: `docs/guides/CREATE_TOOL_GUIDE.md`
- Modify: `docs/guides/model-runtime-packaging.md`
- Modify: `deploy/kubernetes/README.md` only if smoke prerequisites or deployment instructions change

**Step 1: 对齐操作文档**

说明管理员如何从已发布包注册候选 K8s 版本、如何提供模型输入执行 smoke、如何提升/回滚，以及平台不构建镜像的责任边界。明确仓库 Worker 示例需显式部署，实际 K8s、MinIO、Registry readiness 需现场检查。

**Step 2: 执行后端聚焦回归**

Run: `pytest -q test/test_tool_package_api.py test/test_kubernetes_tool_binding.py test/test_task_direct_execution.py test/test_tool_version_promotion_api.py`

Expected: 聚焦后端测试全部通过。

**Step 3: 执行前端聚焦回归与 diff 检查**

Run: `cd frontend && npm test -- src/domain/tool-packages/kubernetes-registration.spec.ts && npm run build`

Expected: 前端测试和构建通过。

Run: `git diff --check`

Expected: 无空白错误。集群端真实 smoke 作为部署验收，不以 mock 测试替代。
