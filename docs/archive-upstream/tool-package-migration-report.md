# Tool Package 迁移报告

## 执行方式

```bash
cd backend && python -m app.cli.migrate_tool_packages --dry-run
cd backend && python -m app.cli.migrate_tool_packages --apply
```

CLI 输出 JSON 汇总：扫描数量、将创建的软件包与版本、已跳过项、无效项以及每个工具版本的具体原因。`--dry-run` 在事务回滚后退出，不会写入数据库。

## 转换规则

- 每个旧 `ToolVersion` 映射为同 slug 的 `ToolPackage` 的一个不可变版本；重复运行会跳过已有 `(package_id, version)`。
- 只复制工具元数据、声明式输入输出、执行器类型和镜像引用。旧配置中的主机、端点、请求头、凭据、宿主路径和环境变量不会进入 manifest。
- 迁移要求启用的 `agent_capability`、语义输入、语义输出和支持的执行器类型。缺失时报告保留原字段路径。
- NVIDIA 只有 `golden_validation.nvidia_cuda.passed=true` 时才标记为 `validated`；否则为 `unvalidated`。
- 海光 DCU 默认为 `adapted_pending_hardware_validation`，只有 `golden_validation.haiguang_dcu.passed=true` 时才标记为 `validated`。

## 发布边界

迁移版本一律为未签名草稿，不能自动发布。管理员须补齐运行镜像、签名和黄金样例验收后，按 Tool Package 发布流程上线。
