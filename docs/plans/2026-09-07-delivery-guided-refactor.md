# Delivery Guided Refactor Plan

> 本计划以 `docs/delivery` 三份企业交付说明书为基线，按 V1 P0 缺口小步重构；每项完成后单独验证并提交。

## 交付基线

- V1 首期交付以两条主链路为验收目标：`Fetch PDB -> Protein Preparation -> LVpocket` 与 `Fetch PubChem -> Ligand Preparation -> RDKit -> 基础 ADMET`。
- V1 地基模块必须优先稳定：Standard Artifact、Tool Contract、Run Preparation、Result Manifest、Task Command、Workflow Hydration、Executor Gateway。
- 前端只展示预检和结果，不复制后端权威的绑定、权限和准备规则。
- 暂不纳入 V1 阻断：K8s/Slurm 生产化、MD 完整生产链路、复杂 Agent 自动执行、保存视图和多轮实验闭环。

## 执行原则

- 只做能直接支撑 V1 P0 验收的小步重构。
- 不新增数据库表或迁移，除非后续验收项确实被阻断。
- 优先抽深模块，减少页面、路由和调度器里的重复规则。
- 每个任务遵循红灯测试、最小实现、定向回归、提交。

## 当前进度

- 2026-09-07：完成任务工作台系统视图查询第一步，新增 `Task View` 查询模块，将 `/api/v1/tasks` 的权限、项目、关键词、状态和系统视图筛选收敛到后端查询入口。
- 已支持 `view=all|running|history|needs_attention|recent_results`；`running` 包含 pending/running，`history` 包含 success/failure/canceled，`needs_attention` 聚焦 failure。
- 前端任务 API 类型已补 `TaskSystemView`，页面暂不改交互，避免过度设计。
- 2026-09-07：完成 Artifact / File 下载审计最小闭环；普通文件下载、ArtifactVersion 主文件下载和 role 文件下载在权限与存储读取通过后记录 `FILE_DOWNLOAD` 审计事件。
- signed URL 下载测试改为内存审计 recorder，避免测试运行时写入真实审计日志污染工作区。
- 2026-09-07：任务中心前端开始携带后端系统视图参数；标签页仍保留本地兜底过滤，但请求已按 `all/running/history` 缩小后端结果集。
- 2026-09-07：任务列表补齐创建时间范围筛选；后端 Task View 查询支持 `created_from/created_to`，前端历史任务日期控件开始透传时间窗口。
- 2026-09-07：任务列表补齐 workflow/node 定位筛选；后端可按 `workflow_run_id`、`workflow_definition_id`、`workflow_node_id` 从 `TaskInput.params` 定位节点任务。
- 2026-09-07：任务列表关键词搜索补齐失败原因字段，可按 `error_message` / `progress_message` 定位需要关注的失败任务。
- 2026-09-07：Result Manifest 失败收口；worker 与 direct recovery 在标准 Artifact 持久化失败时先回滚未提交产物，再把任务标记为失败，避免无效 `result.v2` 进入下游 ArtifactVersion。
- 2026-09-07：Workflow Hydration 补齐保存节点工具选择恢复；加载旧 canvas 节点时可从 `selected_tool_by_node`、`recommendedToolSlug` 或 `toolSlugs` 恢复工具选择，并用当前 Tool Contract 回填 Artifact slots。
- 2026-09-07：任务取消审计进入共用取消入口；独立任务、工作流节点任务和 Agent 关联任务调用 `cancel_platform_task` 成功后统一记录 `TASK_CANCEL` 事件。
- 2026-09-07：文件/Artifact 下载拒绝审计补齐；普通文件越权、令牌无效、未登录和过期拒绝记录 `FILE_DOWNLOAD/DENIED`，Artifact 下载跨项目拒绝在不改变 404 响应的前提下记录内部审计。
- 2026-09-07：基础 ADMET 占位输出防误用；内置 virtual ADMET 未配置真实 endpoint 时，输出显式 `prediction_status=unconfigured`、endpoint/model/unit/applicability 为 unknown、evidence 为 `engineering_smoke_only`，避免把 RDKit 或占位结果冒充真实 ADMET 预测。
- 2026-09-07：Workflow Hydration 预检状态补齐；加载保存工作流后，节点级 Artifact 绑定会进入预检校验，陈旧或语义不匹配的绑定显示为 `invalid_artifact_binding`，避免用户运行时才发现标准产物不可用。
- 2026-09-07：任务中心分页继续服务端化；列表页开始按当前标签、筛选、关键词和页码调用 `/tasks`，展示区直接消费后端页结果，不再对已取回数据做本地二次分页。
- 2026-09-07：Workflow Run 恢复输入选择；加载保存工作流并恢复最新运行时，同步回填 `input_files` 到工作流输入选择，避免节点任务已恢复但预检仍误报缺少 workflow input。
- 2026-09-07：Workflow Run 局部节点重试恢复补齐；节点重试接口返回新 run 后复用同一恢复入口拉取新 `task_id` 详情并回填节点卡片，避免局部重试后画布仍显示旧任务。
- 2026-09-07：Workflow Run 取消恢复补齐；取消工作流运行后复用同一恢复入口同步回填取消后的节点任务和输入选择，避免画布继续显示取消前的运行状态。
- 2026-09-07：Workflow Run 失败定位入口补齐；运行状态面板中带 `task_id` 的节点可直接跳转任务详情，方便从失败节点进入日志和产物排查。
- 2026-09-07：任务中心系统视图计数后端化；新增 `/tasks/counts` 复用任务视图权限、项目、关键词、时间和 workflow 筛选，返回 all/running/history/needs_attention/recent_results 计数，避免为了徽标重新拉全量任务。
- 2026-09-07：任务中心前端接入系统视图计数；标签徽标读取 `/tasks/counts` 结果，筛选、搜索、刷新和自动刷新时同步更新计数，服务端分页后仍保留跨标签数量感知。
- 2026-09-07：任务中心新增需要关注快捷视图；前端标签页直接映射后端 `needs_attention` 系统视图，失败任务可从任务中心独立入口快速定位。
- 2026-09-07：任务中心接入 workflow/node URL 定位参数；列表和系统视图计数都会透传 `workflow_run_id`、`workflow_definition_id`、`workflow_node_id`，支持从工作流上下文打开关联任务列表。
- 2026-09-07：Workflow Run 节点任务列表入口补齐；运行状态面板可从节点跳转任务中心并携带 workflow/run/node 过滤参数，方便查看同一节点的历史和失败任务。

## 下一步候选

1. Workflow Hydration 继续检查：保存加载后恢复失败运行的预检提示和历史状态展示边界场景。
2. 基础 ADMET 真实 endpoint 接入：登记 endpoint、模型版本、单位/标签、模型卡和证据附件后替换占位链路。
3. 任务中心失败定位增强：可继续为任务列表增加从 URL 自动切换 `needs_attention` 的便捷入口。
