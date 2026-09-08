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
- 2026-09-07：任务中心 URL 视图恢复补齐；`/tasks?view=needs_attention` 可直接打开需要关注标签，失败节点入口自动带入该视图，减少失败定位跳转后的手动切换。
- 2026-09-07：Workflow Run 手动同步恢复补齐；用户点击同步最新运行状态后，同步回填 `input_files` 和新节点 `task_id` 详情，避免预检和节点卡片停留在旧任务状态。
- 2026-09-07：任务中心 workflow 过滤上下文提示补齐；列表页在 URL 携带 run/definition/node 定位参数时展示当前过滤范围，避免从工作流跳转后失去来源感。
- 2026-09-08：基础 ADMET 工具口径修正；确认 MolP-PC 是 V1 基础 ADMET 交付工具族，planner 的 `admet_prediction` intent 开始优先路由到 `molp-pc-property-prediction`，内置 builtin ADMET 保留为未配置占位防误用。
- 2026-09-08：MolP-PC 基础 ADMET 交付元数据补齐；Tool Package v2 样例、模型侧 `result_builder` 和 legacy 标准化输出开始携带模型版本、runtime/endpoint、weights、单位/标签策略、证据等级、适用域状态、模型卡和验证记录引用。
- 2026-09-08：MolP-PC 独立运行标准产物补齐；legacy direct/worker 输出标准化时同步生成 `molecule_table@1` 与 `run_report@1`，并建立 report 描述 properties 的 lineage，满足基础 ADMET 表格加科学说明附件的最小验收口径。
- 2026-09-08：AT-003 前端预设入口补齐；工作流画布新增 `PubChem -> Ligand Preparation -> SDF to SMILES -> RDKit Properties -> MolP-PC Basic ADMET` 预设，复用现有工具 slug 和标准 Artifact 类型，不新增运行器特判。
- 2026-09-08：AT-003 预设保存绑定补齐；小分子链路节点开始携带 `artifact_input_slots` / `artifact_outputs`，保存 WorkflowDefinition 时可生成 `node:<upstream>:<slot>` 形式的标准 Artifact 绑定。
- 2026-09-08：AT-003 后端定义验收补齐；后端 Workflow validation 可接收小分子链路标准 Artifact 绑定并按 `Fetch PubChem -> Ligand Preparation -> SDF to SMILES -> RDKit -> MolP-PC` 顺序生成可调度节点，结果节点不再被前端序列化为可执行工具。
- 2026-09-08：AT-003 scheduler 绑定验收补齐；当 RDKit Properties 节点成功产出 `properties` ArtifactVersion 后，MolP-PC 节点调度会把该版本作为 `molecules` 标准输入绑定，并保留关联文件列表。
- 2026-09-08：MolP-PC 科学附件定位补齐；任务输出详情开始从完整 `outputs.result.standard_result` 提取模型卡、验证记录和证据等级引用，用户可在基础 ADMET 结果区直接定位交付附件说明。
- 2026-09-08：AT-003 平台工具调用 smoke 说明补齐；沉淀 `PubChem -> Ligand Preparation -> SDF to SMILES -> RDKit -> MolP-PC` 平台工具调用步骤、通过标准、失败排查和自动化回归命令。
- 2026-09-08：任务失败定位增强；执行器失败时保留 `TaskExecutionError.details` 到任务输出，任务详情页直接展示 stderr/stdout，并对标准产物缺失或 Result Manifest 问题给出醒目提示。
- 2026-09-08：Artifact 详情交付元数据展示补齐；ArtifactVersion API 显式返回 `manifest_json`，文件类/报告类产物卡片展示模型版本、runtime、endpoint、证据等级、模型卡和验证记录等关键交付元数据。
- 2026-09-08：任务失败诊断 API 收敛；任务详情接口新增结构化 `failure_diagnostics` 字段，前端优先消费该字段并保留旧输出 JSON 提取作为兼容兜底。
- 2026-09-08：V1 交付验收索引补齐；新增一页 P0 验收入口，收敛主链路、地基模块、自动化命令、AT-003 smoke 说明和当前限制，便于客户验收前快速巡检。
- 2026-09-08：Artifact 元数据列表筛选补齐；项目 Artifact 列表接口支持按 `manifest_json.metadata.model_version` 和 `manifest_json.metadata.evidence_level` 筛选，前端 API 可直接透传交付元数据筛选参数。
- 2026-09-08：交付验收命令分层补齐；V1 验收索引将命令集拆成 smoke 检查、P0 回归和发布前门禁，便于小步重构后快速验证，交付前再跑完整覆盖。
- 2026-09-08：Executor Gateway 健康面补齐；系统健康接口新增 `executor_gateway` 服务项，展示当前任务后端和 V1 已登记执行器类型，前端系统健康排序和中文标签同步更新。
- 2026-09-08：MolP-PC runtime 依赖预检补齐；本地 AT-003 smoke 发现默认 Python 缺少 `dgl`/`torch`，模型 wrapper 在调用旧推理入口前显式检查 `dgl`、`rdkit`、`torch` 并输出 `admet.yml` / `MOLP_PC_PYTHON` 修复提示，避免误判为平台调度失败。
- 2026-09-08：Artifact 基础检索补齐；项目 Artifact 列表接口支持按 `artifact_type`、`semantic_type`、`standard_type` 和 `source_task_id` 筛选，前端 API 类型同步，支撑 AT-010 类型/来源检索验收。
- 2026-09-08：Artifact role 检索补齐；项目 Artifact 列表接口支持按最新 ArtifactVersion 的 `file_role` 筛选，复用现有 `ArtifactVersionFile.role`，不新增检索表。
- 2026-09-08：Artifact 科学元数据筛选扩展；项目 Artifact 列表接口在已有模型版本和证据等级筛选基础上，补齐 `endpoint_ref` 与 `applicability_domain_status` 筛选，便于定位特定 MolP-PC runtime 或适用域状态结果。
- 2026-09-08：MolP-PC 验收口径纠正；确认 AT-003 主验收必须通过平台注册 `molp-pc-property-prediction`、当前 `ToolVersion`、平台任务创建和 Executor Gateway 调度完成，`model/MolP-PC/platform_run.sh` 只保留为模型包本地调试和执行器 runtime 自检。
- 2026-09-08：AT-003 平台真实运行记录模板补齐；新增 task_id、ToolVersion、输入哈希、输出 ArtifactVersion、科学元数据、下载审计和结论字段，平台 smoke 完成后可直接归档证据。
- 2026-09-08：任务创建响应取证字段补齐；`/tasks` 创建成功后返回 `tool_slug`、`tool_version_id`、当前版本摘要和调度信息，便于 AT-003 平台 smoke 自动化记录 MolP-PC 工具调用证据。

## 下一步候选

1. AT-003 平台工具调用真实运行：在具备 PubChem 网络和 MolP-PC runtime 的平台环境中执行一次 smoke，并按模板归档 task ID、输入哈希、ToolVersion 和输出 ArtifactVersion。
2. AT-003 平台 smoke 自动化：基于平台 API/Workflow runner 收集任务与 Artifact 证据；不得用 `model/MolP-PC/platform_run.sh` 自动化结果替代平台任务验收。
3. Artifact 检索扩展：如产物库规模继续增大，再评估模型族聚合筛选或常用筛选项前端表单化。
