# 生产 Compose CI 验证设计

## 目标

闭环技术债清单 `2.4.5`：让 `deploy/compose/docker-compose.prod.yml` 在每次主分支提交和拉取请求中完成 Compose 配置解析与后端生产镜像构建验证。

## 方案

在现有 `.github/workflows/ci.yml` 中新增独立 `production-compose` job：

1. 使用 GitHub 托管的 Ubuntu runner。
2. 在 job 级别提供仅用于 CI 插值的非生产占位环境变量。
3. 执行 `docker compose -f deploy/compose/docker-compose.prod.yml config --quiet`，验证必填变量、Compose 语法、锚点和服务引用。
4. 执行 `docker compose -f deploy/compose/docker-compose.prod.yml build backend`，验证 `backend/Dockerfile` 的 `production` target 和生产依赖安装。

不在本任务中启动 PostgreSQL、Redis、MinIO、后端或 Worker。服务启动会引入健康检查等待、端口与外部镜像可用性等集成因素，超出“配置可通过 CI 构建验证”的清单范围。后续真实环境部署验收应在具备 Docker 的目标主机执行。

## 安全与可维护性

- CI 占位密钥必须明显标记为测试值，不能来自或模拟生产凭证。
- 不向镜像构建过程传入应用密钥；环境变量只供 Compose 插值。
- 使用独立 job，避免后端/前端测试失败与镜像构建失败互相掩盖。
- 保留现有 `test/test_production_compose.py` 静态结构测试，形成快速本地检查与真实 CI 构建两层验证。

## 测试

先扩展生产 Compose 测试，解析 `.github/workflows/ci.yml` 并断言存在独立 job、配置校验命令、后端构建命令和必填占位环境变量。确认测试失败后再修改 CI，随后运行部署聚焦测试、后端全量测试、前端测试和生产构建。
