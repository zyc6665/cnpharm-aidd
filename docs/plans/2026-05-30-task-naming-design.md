# 任务命名设计

## 目标

为平台任务增加稳定、可读、可搜索的“任务名”能力，解决当前任务主要依赖 `id` 定位、用户难以区分历史任务的问题。

第一版目标：

- 用户创建任务时可以选填任务名
- 未填写时由系统自动生成默认任务名
- 任务列表、任务详情优先展示任务名
- 任务搜索支持按任务名匹配
- 对历史无名称任务保持兼容显示

## 背景与现状

当前任务链路存在三个明显缺口：

### 1. 数据模型里没有任务名

任务模型 [backend/app/models/tasks.py](/data/zhouyc/cpumodel_sciminer/backend/app/models/tasks.py) 当前没有 `name` 字段。

这导致：

- 创建任务时无法保存用户自定义标题
- 列表和详情只能依赖工具名、状态和 `id`
- 后端无法按任务名检索

### 2. 前端有“搜索任务名称或ID”的文案，但后端并不支持

任务列表接口 [backend/app/api/v1/tasks.py](/data/zhouyc/cpumodel_sciminer/backend/app/api/v1/tasks.py) 当前 `keyword` 只匹配：

- `Task.id`
- `Tool.name`
- `Tool.slug`
- `User.email`
- `User.display_name`

并没有匹配任务名称字段。也就是说，前端文案和真实能力不一致。

### 3. 任务创建入口不止一个

当前至少有两条会创建任务的前端链路：

- 单工具页 [frontend/src/views/tools/Detail.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/views/tools/Detail.vue)
- 工作台运行面板 [frontend/src/components/workflow/WorkflowRunPanel.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/components/workflow/WorkflowRunPanel.vue)

如果只改其中一条，用户体验会分裂：

- 单工具页可以命名
- 工作台创建的任务仍然只有默认标题

因此任务命名必须作为“任务创建协议”的统一能力实现，而不是某个页面的局部行为。

## 核心设计决策

### 1. 在 `tasks` 表中持久化 `name`

采用数据库字段持久化，而不是写入 `extra_data` 或只在前端临时拼接。

原因：

- 任务名是稳定的用户数据，不是临时展示态
- 需要支持搜索
- 需要被任务列表、详情、工作台、管理后台一致消费
- 后续如果要支持排序、筛选、批量编辑，也必须有一等字段

设计：

- 在 `Task` 模型新增 `name = Column(String(120), nullable=True, index=True)`

### 2. 任务名为“可选填写，后端兜底生成”

用户可以填，也可以不填。

规则：

- 前端传入非空 `name` 时，后端清洗后保存
- 前端未传或传空字符串时，后端自动生成默认任务名

采用后端兜底的原因：

- 统一所有任务来源
- 防止不同入口生成规则漂移
- 保证 API、批处理或未来其它客户端都能获得同样行为

### 3. 默认任务名使用“工具名 + 时间”

默认格式采用：

- `{工具名} {YYYY-MM-DD HH:mm}`

例如：

- `分子对接 2026-05-30 14:25`

原因：

- 比纯 `id` 更可读
- 同一工具的多次提交容易区分
- 不需要引入额外序号管理

第一版默认使用服务端 `created_at` 对应时间格式化，不处理时区本地化。

### 4. 历史任务不做批量回填，读取时兼容回退

旧任务数据库里没有 `name`，第一版不强制批量补写。

读取时统一规则：

- 优先返回 `task.name`
- 若为空，则返回 `工具名 + 创建时间`
- 若工具信息也缺失，再回退成短 `id`

这样可以：

- 不引入一次性迁移风险
- 保持旧任务页面可读
- 让前端只消费一个稳定的 `name` 字段

### 5. 任务命名能力同时接入单工具页与工作台

任务名输入框需要同时出现在：

- 单工具详情页
- 工作台运行面板

这样才能确保所有普通用户任务入口都一致支持命名。

## 数据与迁移设计

### 模型改动

修改 [backend/app/models/tasks.py](/data/zhouyc/cpumodel_sciminer/backend/app/models/tasks.py)：

- `Task` 新增 `name: str | None`

### 现有数据库迁移

该仓库当前启动逻辑使用 `Base.metadata.create_all()`，它只能创建缺失表，不能修改已存在表结构。

因此要补一份显式 SQL 脚本，例如：

- `backend/scripts/add_task_name_column.sql`

脚本职责：

- 为 `tasks` 表增加 `name` 列
- 为 `name` 建索引（如果数据库支持）

这一步是为了保证现有开发库和部署库都能安全升级。

## 后端接口设计

### Schema 改动

修改 [backend/app/schemas/tasks.py](/data/zhouyc/cpumodel_sciminer/backend/app/schemas/tasks.py)：

- `TaskCreate` 新增 `name: Optional[str]`
- `TaskResponse` 新增 `name: Optional[str]`
- `TaskListResponse` 新增 `name: Optional[str]`

### 创建任务接口

修改 [backend/app/api/v1/tasks.py](/data/zhouyc/cpumodel_sciminer/backend/app/api/v1/tasks.py)：

- 接收 `task_data.name`
- 清洗逻辑：
  - `strip()`
  - 空字符串按未填写处理
  - 长度超过上限时拒绝
- 在 `Task` 创建后，如果 `name` 为空则生成默认名称并写回

建议把命名逻辑收敛为私有 helper，例如：

- `_sanitize_task_name(...)`
- `_build_default_task_name(...)`
- `_resolve_task_display_name(...)`

### 列表与详情响应

列表和详情统一返回 `name` 字段。

对旧任务：

- 若数据库 `name` 为空，则响应层返回回退后的展示名

这样前端不需要自行重复实现默认命名逻辑。

### 列表搜索

任务列表 `keyword` 搜索新增：

- `Task.name.ilike(search_pattern)`

这样前端现有“搜索任务名称或ID...”文案才能成立。

## 前端设计

### 类型与 API

修改：

- [frontend/src/types/models.d.ts](/data/zhouyc/cpumodel_sciminer/frontend/src/types/models.d.ts)
- [frontend/src/api/tasks.ts](/data/zhouyc/cpumodel_sciminer/frontend/src/api/tasks.ts)
- [frontend/src/stores/tasks.ts](/data/zhouyc/cpumodel_sciminer/frontend/src/stores/tasks.ts)

内容：

- `Task` 增加 `name?: string`
- `TaskCreateParams` 增加 `name?: string`

### 单工具页

在 [frontend/src/views/tools/Detail.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/views/tools/Detail.vue) 参数表单顶部增加：

- `任务名称` 输入框
- 非必填
- 占位文案：`可选，留空将自动生成`

提交任务时把该字段一并传给 `tasksStore.createTask(...)`。

### 工作台运行面板

在 [frontend/src/components/workflow/WorkflowRunPanel.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/components/workflow/WorkflowRunPanel.vue) 同样增加：

- 可选任务名称输入框
- 提交时传入 `name`

### 任务列表

修改 [frontend/src/views/tasks/List.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/views/tasks/List.vue)：

- 主标题优先显示 `task.name`
- 次级信息保留工具名和短 `id`

建议表现形式：

- 主标题：任务名
- 副标题：`工具名 · ID: 1234abcd...`

### 任务详情

修改 [frontend/src/views/tasks/Detail.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/views/tasks/Detail.vue)：

- 页面主标题显示 `task.name`
- 工具信息作为辅助字段保留

### 工作台状态引用

工作台会把任务摘要存进 session store：

- [frontend/src/workflow/artifact-types.ts](/data/zhouyc/cpumodel_sciminer/frontend/src/workflow/artifact-types.ts)
- [frontend/src/workflow/task-state.ts](/data/zhouyc/cpumodel_sciminer/frontend/src/workflow/task-state.ts)

这里也应补上 `name`，避免工作台后续展示任务引用时丢失命名信息。

## 兼容性策略

### 对历史任务

不要求数据库立即回填旧记录。

通过后端响应层兼容：

- 老任务没有 `name` 也能显示默认标题

### 对当前前端

老页面如果还在读取工具名，不会立刻崩溃；只是不会利用新字段。

因此可以渐进式切换展示逻辑。

## 测试策略

### 后端

新增 `pytest` 用例覆盖：

- 创建任务时传入 `name` 能保存并返回
- 不传 `name` 时会生成默认任务名
- 列表接口返回 `name`
- `keyword` 可以命中任务名
- 旧任务 `name` 为空时仍返回回退展示名

### 前端

新增 `node:test` 表面测试覆盖：

- 单工具页存在任务名称输入框
- 工作台运行面板存在任务名称输入框
- 两处提交都把 `name` 传给 `createTask`
- 任务列表和详情优先展示 `task.name`

## 风险与边界

### 1. 默认名称可能重复

允许重复。

原因：

- 任务名主要用于人类识别，不作为唯一键
- 唯一约束会徒增复杂度

### 2. 第一版不做“编辑任务名”

本次只覆盖创建与展示。

不做：

- 创建后重命名
- 批量命名
- 历史任务批量补名

这是明确的 YAGNI 取舍。

### 3. 默认名称时间不做本地化

第一版直接使用服务端时间格式生成，避免把时区与国际化一起卷入本次需求。

## 结论

本次需求的正确落点不是“前端把标题换一下”，而是：

- 为任务引入持久化 `name`
- 在所有任务创建入口支持可选命名
- 由后端统一生成默认标题
- 在列表、详情和搜索链路中统一消费

这能以最小复杂度，把“任务只有 id 不好用”的核心问题一次解决。
