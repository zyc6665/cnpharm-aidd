# AIDD 首月上线验收

> 状态说明：本文记录的是 2026-07-31 的代码与自动化验收边界。只有带有真实环境证据的项目才可以在发布单中标为“生产已验证”。

## 目标闭环

验收对象是项目、研究会话、Agent 计划与审批、LVpocket 执行、Artifact 和整页科研白板：用户在同一项目中发起口袋识别，审批后执行，将产物沉淀并引用到项目白板；刷新或 SSE 重连后仍能恢复状态。

## 已验项目

| 项目 | 状态 | 证据/命令 |
| --- | --- | --- |
| 项目隔离与成员角色 | 自动化已验 | `pytest test/test_projects_api.py test/test_project_conversations_api.py -q` |
| 会话、不可变消息、计划审批与事件续传 | 自动化已验 | `pytest test/test_project_conversations_api.py test/test_agent_event_stream.py -q` |
| LVpocket NVIDIA 变体选择、审批门禁与 ExecutionPort 提交 | Fake 执行已验 | `pytest test/test_project_agent_lifecycle.py test/test_aidd_vertical_slice.py -q` |
| Artifact 类型、版本、谱系与受保护下载 | 自动化已验 | `pytest test/test_typed_artifacts_api.py test/test_artifact_lineage.py -q` |
| 项目 Artifact 引用到整页科研白板 | 自动化已验 | `pytest test/test_project_research_boards_api.py test/test_aidd_vertical_slice.py -q` |
| 离线运行时依赖与生产 Compose 契约 | 静态已验 | `pytest test/test_aidd_production_compose.py -q` |

“Fake 执行已验”仅证明平台契约：签名且有效的 LVpocket 包选择 `nvidia-cuda` 变体，审批后经 ExecutionPort 提交，并可产生可引用 Artifact。它不替代 NVIDIA 实机黄金样例和科学结果复核。

## NVIDIA 实机验收

在具备 NVIDIA 驱动、CUDA 运行时、目标镜像、SSH 执行节点与 MinIO/PostgreSQL/Redis 的预发布环境执行：

```bash
pytest test/test_lvpocket_tool_package.py test/test_execution_port.py -q
cd backend && python -m app.tool_packages.validator ../example/tool-package-lvpocket
docker compose -f ../docker-compose.prod.yml config
```

随后以受控测试账号上传已登记 SHA-256 的 PDB 黄金样例，完成“创建项目 -> 研究会话 -> 审批 -> LVpocket -> Artifact -> 白板”流程。发布记录必须保存：工具包版本与签名摘要、镜像摘要、GPU 型号和驱动版本、输入哈希、输出 Artifact 哈希、数值容差对比、Agent Run ID、审批人和时间。

未提供以上真实运行证据前，发布状态只能标记为“平台契约已验”，不得声称 LVpocket NVIDIA 生产结果已验证。

## 海光 DCU 验收

DCU 目前是待硬件验收状态。工具包可声明 `haiguang_dcu` 变体，但在海光 x86_64 + 麒麟/UOS + DCU 真机完成同一黄金样例前，验证等级必须保持 `adapted_pending_hardware_validation`。不得以 NVIDIA 结果、容器可构建结果或静态校验替代 DCU 真机结论。

需要记录 DCU 型号、驱动和 ROCm/DTK 版本、操作系统版本、镜像摘要、输入输出哈希、容差及失败日志。

## 功能开关与发布顺序

当前首月计划定义以下开关。部署前必须在配置层落地并记录每个环境的实际值；管理员可通过 `/api/v1/system/feature-flags` 审计解析后的状态、来源和说明。

```text
AIDD_PROJECT_WORKSPACE_ENABLED
AIDD_PROJECT_CONVERSATIONS_ENABLED
TOOL_PACKAGE_V1_ENABLED
PROJECT_RESEARCH_BOARD_ENABLED
LEGACY_AIDD_API_ENABLED
```

推荐顺序：先部署兼容代码与迁移，所有新入口保持关闭；执行 backfill dry-run 并核对；只向内部测试用户开放；完成 NVIDIA 黄金闭环；灰度普通用户；稳定一个发布周期后再评估旧入口和旧字段的移除。

## 回滚

1. 停止扩大灰度，关闭项目工作台、会话、Tool Package v1 和项目白板入口，保留 `LEGACY_AIDD_API_ENABLED`。
2. 回退应用镜像至上一已知可用版本，保留 PostgreSQL、MinIO Artifact 和审计记录。
3. 不对已产生的 Artifact、审批和项目数据做删除式回滚；先导出故障时间窗的 Agent 事件、执行请求与日志。
4. 只有在已验证备份恢复演练的情况下才执行数据库 downgrade 或恢复。应用回滚优先于破坏性数据回滚。
5. 记录受影响项目、Artifact 哈希、审批和执行 ID，修复后从相同黄金输入重跑验证。

## 发布前命令

```bash
pytest -q test
cd frontend && npm test -- --run
cd frontend && npm run build
cd backend && alembic heads
cd backend && alembic current
git diff --check
```

## 尚未执行或待补项

- 未配置 Playwright 与 `test:e2e`，因此未执行真实浏览器登录、上传、刷新及断线恢复测试；不要在验收阶段临时引入该依赖。
- 未执行 NVIDIA 真机 LVpocket 黄金样例；当前自动化使用 Fake ExecutionPort。
- 未执行海光 DCU 真机验收。
- 未对 200 节点白板做浏览器性能基准，也未采集首次 SSE 事件小于 2 秒、任务状态小于 3 秒的环境指标。
- 当前已具备统一运行时配置读取、管理员审计接口和核心业务路由拦截；后续仍需补齐灰度用户分组。
