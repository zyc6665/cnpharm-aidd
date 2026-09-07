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

## 下一步候选

1. Result Manifest 校验与 TaskOutput 持久化收口：确保输出不合规时不给下游生成标准 Artifact。
2. Workflow Hydration 恢复检查：保存加载后恢复节点任务、Artifact 绑定和预检状态。
3. 基础 ADMET 交付链路盘点：确认真实 endpoint、模型版本、单位和模型卡附件是否齐全。
4. 任务中心分页继续服务端化：后续可移除标签内的前端二次分页，直接使用 `/tasks` total。
