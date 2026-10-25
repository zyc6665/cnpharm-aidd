# 任务中心 Agent 会话分组设计

## 背景

当前任务中心把所有工具任务平铺展示。AIDD agent 一次会话会创建多个工具任务，这些 step 任务混在普通任务中，导致列表过长，也削弱了“同一次智能体运行”的上下文。

## 目标

任务中心默认用一个 Agent 会话卡片代表一次 agent run，并把该 run 下的工具任务收纳到卡片内。卡片默认折叠，用户点击后展开查看该会话使用的工具任务。

## 推荐方案

前端任务中心同时加载：

- `/api/v1/tasks`：普通工具任务列表。
- `/api/v1/agents/aidd/runs`：agent 会话及 steps。

前端根据 `agent_run.steps[].task_id` 生成 task id 集合，把这些工具任务从普通任务列表中隐藏，再为每个 agent run 渲染一张聚合卡片。

## 卡片行为

- 默认折叠。
- 点击 Agent 卡片切换展开状态。
- 卡片标题优先使用 `run.summary`，其次使用 `run.message`。
- 卡片状态来自 `run.status`。
- 卡片显示 step 总数、已完成数、失败数、创建时间和完成时间。
- 展开后显示 steps 列表：步骤名、工具 slug、状态、关联任务入口。
- 有 `task_id` 的 step 可进入任务详情。
- 失败 step 显示 `error_message`。

## 列表筛选规则

- `all`：展示普通工具任务 + agent 会话卡片。
- `running`：展示运行/等待中的普通工具任务 + 非终态 agent 会话卡片。
- `history`：展示终态普通工具任务 + 终态 agent 会话卡片。
- 工具筛选只影响普通工具任务；agent 会话中如果任一 step 的 `tool_id` 匹配，则保留该 agent 卡片。
- 关键词搜索匹配普通任务名称/工具名/ID，也匹配 agent message/summary/run id/step tool slug。

## 技术边界

本次先不改后端分页接口。由于当前 `/agents/aidd/runs` 已返回 run + steps，前端可以完成首版分组。后续如果数据量变大，再考虑新增后端统一 timeline 接口。

## 风险

如果当前任务页只加载一页 `/tasks`，某些 agent step 对应的工具任务可能不在当前页。首版展开列表可先基于 step 本身展示状态和 task_id，并提供详情入口；不强依赖完整 task 对象。普通列表隐藏逻辑只隐藏当前页中可见的 agent step task，避免误删其它数据。
