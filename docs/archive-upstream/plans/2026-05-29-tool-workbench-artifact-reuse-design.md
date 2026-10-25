# 工具工作台与产物复用设计

## 目标

将当前强调顺序编排的“流程工作台”收敛为更符合真实科研使用习惯的“工具工作台”：

- 左侧按工具分组组织平台能力，而不是强制步骤推进
- 管理员可以在后台管理分组、工具归属、排序、推荐和显示状态
- 用户在工作台和普通工具页都可以从自己历史任务的输出文件中手动选择产物复用
- 第一版只复用当前用户自己的任务输出文件，不处理文本结果、结构化结果或自动流程串联

## 背景与现状

当前代码已经具备三类基础能力：

- 工具管理与分类：
  - [backend/app/models/tools.py](/data/zhouyc/cpumodel_sciminer/backend/app/models/tools.py)
  - [backend/app/api/v1/tools.py](/data/zhouyc/cpumodel_sciminer/backend/app/api/v1/tools.py)
  - [frontend/src/views/admin/ToolCategories.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/views/admin/ToolCategories.vue)
- 单工具运行与任务提交：
  - [frontend/src/views/tools/Detail.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/views/tools/Detail.vue)
  - [frontend/src/views/tools/detail-schema.ts](/data/zhouyc/cpumodel_sciminer/frontend/src/views/tools/detail-schema.ts)
- 文件与任务输出：
  - [backend/app/models/tasks.py](/data/zhouyc/cpumodel_sciminer/backend/app/models/tasks.py)
  - [backend/app/models/files.py](/data/zhouyc/cpumodel_sciminer/backend/app/models/files.py)
  - [backend/app/api/v1/files.py](/data/zhouyc/cpumodel_sciminer/backend/app/api/v1/files.py)

现有 `/workflow` 页面已经实现了一版强流程前端工作台，但这版设计存在明显偏差：

- 它假设用户按固定顺序使用工具
- 它依赖“自动输入输出绑定”来串联上下游
- 它的状态模型围绕“下一步”和“结果失效传播”构建
- 它不适合用户跳步使用、横向比较不同工具或自由复用历史结果

用户已经明确提出新的产品方向：

- 不做强自动流程
- 不要求用户按步骤使用
- 更希望保留工具分组和导航能力
- 更希望通过“选择历史输出文件”完成手动复用

## 核心设计决策

### 1. 将流程步骤改为工作台分组

不再把左侧结构定义为“步骤”，而定义为“工具分组”。

原因：

- 平台需要的是导航结构，不是工作流引擎
- 用户可能从任意环节进入
- 同一个工具后续也可能需要出现在多个研究语境里
- “步骤状态机”会持续把产品往强编排方向推

第一版分组仍然沿用现有五类研究语义，但表达改为：

- 口袋预测
- 分子生成或虚拟筛选
- 分子对接及结合亲和力预测
- 性质预测
- 先导优化

它们是“分组”，不是“必须依次执行的步骤”。

### 2. 工具分类与工作台分组解耦

保留现有 `tool_categories` 不动，不直接拿来做工作台左栏。

原因：

- `tool_categories` 是后台管理分类
- 工作台分组是前台产品导航结构
- 两者语义不同，强行复用会导致后台配置和前台体验互相污染

因此新增一套独立建模：

- `tool_workbench_groups`
- `tool_workbench_group_mappings`

### 3. 产物复用只做“输出文件复用”

第一版只复用当前用户自己历史任务的输出文件。

明确不做：

- 文本结果复用
- `output_data` 结构化结果复用
- 自动把上一步结果映射到下一个字段
- 跨用户共享产物

原因：

- 任务提交协议本来就支持 `file_ids`
- 文件型参数是最稳、最明确的复用对象
- 不引入脆弱的自动绑定规则可以显著降低维护成本

### 4. 不新建独立产物表

第一版“我的产物”直接复用现有任务输出和文件模型：

- `TaskOutput.file_ids`
- `File.source_type == tool_output`

这样“我的产物”只是一个用户视角的输出文件列表，不是新的领域对象系统。

好处：

- 不重复存储
- 不增加生命周期维护负担
- 能直接使用现有下载、权限和文件元数据能力

## 数据模型

### 新增表：`tool_workbench_groups`

字段建议：

- `id`
- `name`
- `slug`
- `description`
- `sort_order`
- `is_enabled`
- `created_at`
- `updated_at`

用途：

- 定义前台工具工作台左侧分组
- 控制显示顺序和启用状态

### 新增表：`tool_workbench_group_mappings`

字段建议：

- `id`
- `tool_id`
- `group_id`
- `sort_order`
- `is_recommended`
- `is_enabled`
- `created_at`
- `updated_at`

约束建议：

- `tool_id + group_id` 唯一
- 外键关联 `tools.id` 和 `tool_workbench_groups.id`

用途：

- 控制某个工具属于哪些分组
- 控制在分组内的排序
- 控制是否推荐、是否显示

### 不新增产物表

“我的产物”通过查询拼装：

- 当前用户的任务
- 任务的输出文件 ID
- 对应文件记录

建议额外返回的聚合信息：

- 来源任务 ID
- 来源工具 ID / slug / name
- 输出时间
- 下载 URL

## 后端接口设计

### 管理端：工作台分组管理

- `GET /api/v1/admin/workbench-groups`
- `POST /api/v1/admin/workbench-groups`
- `PUT /api/v1/admin/workbench-groups/{id}`
- `POST /api/v1/admin/workbench-groups/reorder`

职责：

- 管理分组名称、描述、排序、启停

### 管理端：工具分组映射管理

- `GET /api/v1/admin/workbench-group-mappings`
- `POST /api/v1/admin/workbench-group-mappings`
- `PUT /api/v1/admin/workbench-group-mappings/{id}`
- `DELETE /api/v1/admin/workbench-group-mappings/{id}`

职责：

- 配置工具属于哪些分组
- 设置分组内排序
- 设置推荐与显示状态

### 前台：工作台分组读取

- `GET /api/v1/tools/workbench-groups`

返回建议：

- 启用中的分组
- 每个分组下当前可见、可发布的工具
- 按分组排序和组内排序展开
- 标注推荐工具

### 前台：我的产物读取

- `GET /api/v1/files/artifacts`

查询规则：

- 只返回当前登录用户自己的任务输出文件
- 只返回 `source_type = tool_output`
- 排除已删除、无权限或不可访问文件

支持的基础参数：

- `page`
- `page_size`
- `search`

返回字段建议：

- `file_id`
- `filename`
- `content_type`
- `size_bytes`
- `created_at`
- `download_url`
- `task_id`
- `tool_id`
- `tool_name`
- `tool_slug`

## 前端页面设计

### `/workflow` 页面定位调整

路由保留 `/workflow`，但产品文案从“流程工作台”调整为“工具工作台”。

原因：

- 避免再把页面描述成顺序编排器
- 保持原入口不变，减少前端路由层面波动

### 页面布局

采用三栏结构：

- 左栏：工具分组栏
- 中栏：工具列表与当前工具表单
- 右栏：我的产物

#### 左栏：工具分组栏

展示：

- 分组名称
- 分组说明
- 分组下工具数量
- 当前分组选中状态

不再展示：

- 步骤状态
- 下一步提示
- 结果失效传播

#### 中栏：工具区

展示：

- 当前分组下工具列表
- 推荐工具标记
- 当前选中工具的简要说明
- 当前选中工具的参数表单
- 运行按钮
- 查看工具详情按钮

推荐交互：

- 在工作台中直接运行工具
- 同时保留跳转到 `/tools/:id` 的入口

#### 右栏：我的产物

展示当前用户自己的输出文件：

- 文件名
- 来源工具
- 来源任务
- 生成时间
- 下载入口

建议支持：

- 搜索
- 最近产物优先排序
- 点击后用于填充文件型参数

## 通用“产物文件选择器”

### 核心思想

不改现有任务提交协议，只增强文件型参数的输入来源。

现在文件型参数只有一种来源：

- 本地上传

改造后提供两种来源：

- 本地上传
- 从我的产物选择

最终无论哪种来源，提交层都统一落成 `file_id`。

### 组件职责

建议新增一个通用组件，供两个入口复用：

- 工具工作台页面
- 普通工具详情页 `/tools/:id`

组件能力：

- 切换“上传”/“从我的产物选择”
- 拉取当前用户产物列表
- 选择一个文件并回传 `file_id`
- 展示当前已选文件摘要

### 权限与空态

- 未登录用户：不显示“从我的产物选择”，只保留上传
- 没有历史输出：展示空态提示
- 文件已失效或被删除：不出现在可选列表中

## 迁移策略

### `/workflow` 页面平滑替换

不长期保留“旧流程工作台”和“新工具工作台”双轨。

策略：

- 保留路由
- 替换页面内部语义与交互
- 瘦身现有 workflow store 和 workflow 目录中的强流程逻辑

### 现有工作流逻辑的处理原则

保留可复用部分：

- 工具加载能力
- 工具详情动态表单能力
- 三栏布局基础

移除或废弃部分：

- 自动输入输出绑定
- 下游失效传播
- 下一步推进文案
- 围绕 `activeStepKey` 的强流程状态

## 测试边界

### 后端

- 模型与 schema 测试
  - 工作台分组模型存在
  - 工具分组映射模型存在
- 权限测试
  - 管理员可管理分组与映射
  - 非管理员不可管理
- 数据范围测试
  - `GET /files/artifacts` 只返回当前用户自己的工具输出文件
  - 不返回他人文件
  - 不返回非工具输出文件

### 前端

- 表面测试
  - `/workflow` 页面文案改成工具工作台
  - 左栏为分组而非步骤
  - 后台存在工作台分组管理入口
  - 普通工具页出现“从我的产物选择”
- 逻辑测试
  - 分组排序正确
  - 推荐工具优先显示
  - 选择历史产物后生成正确 `file_ids`
- 构建验证
  - `node --test ...`
  - `vue-tsc -b`
  - `npm run build`

## 非目标

第一版明确不做：

- 自动流程编排
- 自动字段映射
- 文本和结构化结果复用
- 跨用户共享产物
- 拖拽式 pipeline builder
- 新的独立产物生命周期系统

## 推荐实现顺序

1. 后端建模与管理接口
2. 前台分组工作台数据接口
3. “我的产物”接口
4. 通用产物文件选择器
5. 工作台页面从流程语义迁移到分组语义
6. 普通工具详情页接入产物选择器

这个顺序能保证平台先具备可管理的数据结构，再逐步替换前台使用方式，避免前端提前绑定不存在的后端接口。
