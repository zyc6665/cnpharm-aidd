# Docker Compose 部署

本目录按用途保留三套 Compose 配置：

- `docker-compose.dev.yml`：本地 AIDD 开发环境，包含 PostgreSQL、Redis、MinIO、API、Celery Worker 和 Flower。
- `docker-compose.prod.yml`：生产环境基线，启动前需在环境中设置必需密钥。
- `docker-compose.k100-test.yml`：K100 硬件验证环境，需先从当前目录的 `.env.k100-test.example` 创建本地 `.env.k100-test`。

从仓库根目录执行：

```sh
docker compose -f deploy/compose/docker-compose.dev.yml config
docker compose -f deploy/compose/docker-compose.prod.yml config
docker compose --env-file deploy/compose/.env.k100-test.example -f deploy/compose/docker-compose.k100-test.yml config
```

模型镜像归档、开发日志、数据库文件和本地密钥不应提交到 Git。模型镜像归档保留在本机的 `model-build/` 目录中，按模型构建流程传递。
