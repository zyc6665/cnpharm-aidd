# Workflow Definition Run Design

## 背景

当前平台正在统一项目工作台、Agent、Workflow 与标准 Artifact 的执行链路。项目总览已经能够聚合 `WorkflowDefinition`，但 `/workflow?project_id=...` 仍然没有完整消费项目上下文。同时，旧 `WorkflowTemplate -> WorkflowRun` 运行模型没有真实测试数据和继续保留价值，会造成定义态、运行态、任务和 Artifact 之间的归属分裂。

本设计将工作流主线收敛为：

```text
Project
  -> WorkflowDefinition
      -> WorkflowRun
          -> Task
              -> ArtifactVersion
```

## 已确认决策

- `WorkflowTemplate` 下线并删除，不保留 deprecated 入口。
- 数据库同步清理：删除 `workflow_templates` 表，删除旧 template-based run 数据，删除 `workflow_runs.template_id`。
- 复用 `workflow_runs` 表，新增并强制使用 `workflow_definition_id` 作为唯一上游。
- 新运行入口以 `WorkflowDefinition` 为归属：`POST /api/v1/workflows/{workflow_id}/runs`。
- `/workflow?project_id=...` 采用严格项目模式，只加载、保存、复制和运行当前项目的工作流定义。
- 运行前自动保存当前 `WorkflowDefinition`，保存失败则不创建 run。
- 前端删除逐节点直接 `createTask` 的运行路径，统一由后端 `WorkflowRun` 调度节点任务。
- 旧 `WorkflowTemplate` 数据和旧 template-based `WorkflowRun` 数据全部丢弃，不做迁移保留。

## 后端设计

### 数据模型

`WorkflowRun` 改为引用 `WorkflowDefinition`：

```text
workflow_runs.workflow_definition_id -> workflow_definitions.id
workflow_runs.project_id             -> workflow_definitions.project_id
workflow_runs.owner_id               -> current_user.id
workflow_runs.definition             -> WorkflowDefinition 当前快照
```

`WorkflowRun.project_id` 从 `WorkflowDefinition.project_id` 继承。若定义属于项目，创建、列表、查看和同步都必须校验项目成员权限。

### 数据库迁移

迁移策略为硬清理：

1. 删除旧 `workflow_runs` 数据。
2. 新增 `workflow_runs.workflow_definition_id` 外键并设为非空。
3. 删除 `workflow_runs.template_id` 外键、索引和字段。
4. 删除 `workflow_templates` 表。
5. 移除 ORM、schema、service、API 中的 `WorkflowTemplate` 引用。

因为旧模板模型无真实数据价值，不做旧 run 到新 definition run 的猜测迁移。

### API

保留并强化：

```text
GET    /api/v1/workflows
POST   /api/v1/workflows
GET    /api/v1/workflows/{workflow_id}
PUT    /api/v1/workflows/{workflow_id}
DELETE /api/v1/workflows/{workflow_id}
```

新增/替换运行接口：

```text
POST /api/v1/workflows/{workflow_id}/runs
GET  /api/v1/workflows/runs?workflow_definition_id=...&project_id=...
GET  /api/v1/workflows/runs/{run_id}
POST /api/v1/workflows/runs/{run_id}/sync
```

删除旧模板接口：

```text
/api/v1/workflows/templates*
```

### 调度

`WorkflowRun` 创建时，后端从 `WorkflowDefinition` 复制快照到 `WorkflowRun.definition`，校验 definition，生成 `execution_order` 和初始 `node_states`。scheduler 创建节点 Task 时统一传递 `project_id=run.project_id`，标准 Artifact 服务继续从 Task 项目上下文持久化产物。

## 前端设计

### 严格项目模式

`/workflow?project_id=...` 进入项目工作流模式：

- 已保存流程下拉只请求 `GET /workflows?project_id=...`。
- 保存、复制、Agent 草稿保存都自动带 `project_id`。
- 新建流程不脱离当前项目上下文。
- 运行历史请求 `GET /workflows/runs?project_id=...`，当前定义历史追加 `workflow_definition_id`。
- 页面显示当前项目上下文提示，避免用户误以为正在编辑全局流程。

`/workflow` 无 `project_id` 时保留全局模式。

### 运行流程

点击“启动运行”时：

1. 构建当前画布的 `WorkflowDefinitionPayload`。
2. 若没有当前 definition id，则创建 definition。
3. 若已有当前 definition id，则更新 definition。
4. 调用 `POST /workflows/{workflow_id}/runs`。
5. 加载 active run，并通过 sync/轮询刷新节点状态。

前端不再逐节点直接调用 `tasksStore.createTask()` 作为工作流运行路径。

## 测试策略

### 后端

- `WorkflowDefinition` 创建 run 会继承 `workflow_definition_id`、`project_id` 和 definition 快照。
- 非项目成员不能创建、列出、查看、同步项目 workflow run。
- `GET /workflows/runs` 支持 `workflow_definition_id` 与 `project_id` 过滤。
- `/workflows/templates*` 旧接口不再存在。
- Alembic dry run 能看到删除模板表、删除 `template_id`、新增 `workflow_definition_id`。

### 前端

- `/workflow?project_id=project-1` 加载定义列表时传 `project_id`。
- 项目模式保存/复制 definition 自动带 `project_id`。
- 点击运行先保存 definition，再调用新 run 接口。
- 项目模式加载 run history 时传 `project_id`。
- 页面不再渲染旧模板入口或旧逐节点直接运行行为。

## 分批实施

1. 后端模型、schema、service、API 与 Alembic 迁移切到 `WorkflowDefinition -> WorkflowRun`。
2. 后端测试从 template-run 改为 definition-run，并删除模板接口测试。
3. 前端 API/types/store 移除 WorkflowTemplate，新增 definition-run 调用。
4. 前端工作流页读取 `project_id` query，保存/复制/运行/历史统一项目上下文。
5. 删除逐节点 direct Task execution 路径或将按钮替换为标准 WorkflowRun 启动。
6. 全量回归、review、提交。
