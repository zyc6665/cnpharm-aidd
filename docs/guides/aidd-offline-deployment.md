# AIDD 离线与信创环境部署指南

本文面向内网、离线或信创环境部署 CPUModel / SciTool AIDD 平台。平台前后端按
Docker 容器化部署，模型推理和高性能计算任务可通过工具包变体接入 NVIDIA GPU
服务器、海光 x86_64 + 麒麟/UOS 主机或独立计算集群。

## 适用范围

- 操作系统：麒麟、UOS、主流 Linux 发行版。
- CPU 架构：x86_64，重点覆盖海光 x86_64。
- 加速设备：NVIDIA GPU；海光 DCU 可声明适配状态，但真机验收前必须标记为
  `adapted_pending_hardware_validation`。
- 平台服务：FastAPI 后端、Vue 前端、PostgreSQL、Redis、MinIO、Celery Worker。
- 模型运行：容器内任务、SSH Job、远程集群或后续 Slurm/Kubernetes 适配器。

不在本指南中承诺国产数据库、LDAP、Slurm、Kubernetes 或 DCU 真机验证已经完成。

## 离线镜像准备

在联网构建机上构建和导出镜像：

```bash
docker compose -f docker-compose.prod.yml build
docker save \
  scitool-backend:${APP_VERSION:-latest} \
  postgres:16-alpine \
  redis:7-alpine \
  minio/minio:RELEASE.2024-06-13T22-53-53Z \
  -o scitool-aidd-images.tar
sha256sum scitool-aidd-images.tar > scitool-aidd-images.tar.sha256
```

在离线服务器导入前先校验哈希：

```bash
sha256sum -c scitool-aidd-images.tar.sha256
docker load -i scitool-aidd-images.tar
```

如果使用内网镜像仓库，应将镜像重新打标并推送到内网仓库，再在
`docker-compose.prod.yml` 或部署覆盖文件中替换镜像地址。

## 环境变量

生产环境必须显式配置以下变量，不允许使用开发默认值：

```bash
ENVIRONMENT=production
DEBUG=false
POSTGRES_PASSWORD=<强随机密码>
REDIS_PASSWORD=<强随机密码>
MINIO_ROOT_USER=<对象存储账号>
MINIO_ROOT_PASSWORD=<强随机密码>
JWT_SECRET_KEY=<不少于32字符且独立随机>
SETTINGS_ENCRYPTION_KEY=<不少于32字符且不同于JWT密钥>
CORS_ORIGINS=["https://aidd.example.local"]
```

生产配置必须满足：

- `DATABASE_URL` 使用 PostgreSQL。
- `CACHE_BACKEND=redis`。
- `STORAGE_BACKEND=minio`。
- `TASK_EXECUTION_BACKEND=celery`。
- API 和 Worker 不挂载 `/var/run/docker.sock`。
- 前端运行壳不依赖 Google Fonts、CDN 或公网脚本。

## 启动顺序

1. 导入离线镜像并准备 `.env`。
2. 启动 PostgreSQL、Redis、MinIO。
3. 执行数据库迁移。
4. 启动后端 API 和 Celery Worker。
5. 部署前端静态资源或由网关指向构建产物。

示例：

```bash
docker compose -f docker-compose.prod.yml --env-file .env up -d postgres redis minio
docker compose -f docker-compose.prod.yml --env-file .env run --rm backend alembic upgrade head
docker compose -f docker-compose.prod.yml --env-file .env up -d backend celery-worker
```

若当前服务器有 NVIDIA GPU Worker：

```bash
docker compose -f docker-compose.prod.yml --env-file .env --profile gpu up -d celery-worker-gpu
```

## NVIDIA GPU 与海光 DCU

NVIDIA 任务必须在 Tool Package 变体中声明：

- `accelerator: nvidia_cuda`
- `resources.devices`，例如 `nvidia.com/gpu`
- `resources.driver`，例如 `>=535`
- 黄金样例、输入哈希、输出哈希和运行记录

只有完成真实 NVIDIA 环境验收后，才能标记为 `validated`。

海光 DCU 任务必须在 Tool Package 变体中声明：

- `accelerator: haiguang_dcu`
- `resources.devices`，例如 `hygon.com/dcu`
- `resources.driver`
- `validation_status: adapted_pending_hardware_validation`

在没有海光 DCU 真机时，平台只能表示“代码已适配、硬件待验收”，不得在 UI 或文档中宣称
“生产已验证”。

## 模型集群接入

平台容器负责项目、审批、Artifact、事件和审计。模型运行可以放在独立集群：

- 使用 Tool Package 描述输入输出、运行入口、资源和验证等级。
- 通过 SSH Job 或 ExecutionPort 适配器提交到集群。
- 集群凭据只放在部署密钥或运行时配置，不写入 Tool Package、Git 或日志。
- 输出先进入平台对象存储，再登记为不可变 Artifact。
- 失败必须返回明确状态、日志摘要和可重试边界。

## 备份与恢复

上线前必须演练：

- PostgreSQL 逻辑备份与恢复。
- MinIO bucket 备份与对象哈希抽检。
- Redis 丢失后的任务状态恢复策略。
- `.env`、密钥和镜像包的离线介质保管。

最小恢复顺序：

1. 恢复 PostgreSQL。
2. 恢复 MinIO 对象。
3. 导入同版本镜像。
4. 启动 Redis、API、Worker。
5. 执行 Artifact 谱系和项目权限抽检。

## 验收命令

在有 Docker CLI 的环境执行：

```bash
docker compose -f docker-compose.aidd-dev.yml config
docker compose -f docker-compose.prod.yml config
```

代码侧静态验收：

```bash
pytest test/test_aidd_production_compose.py -q
cd frontend && npm test -- --run test/no-public-runtime-dependencies.test.ts
cd frontend && npm run build
```

上线抽检：

- `GET /api/v1/system/health` 返回正常。
- 普通用户可以访问 `/workspace`、项目研究页和科研白板。
- 创建项目、上传蛋白 Artifact、发起 Agent 计划、审批后产生执行事件。
- NVIDIA LVpocket 黄金样例可生成 Pocket Artifact。
- DCU 变体在 UI 中显示待硬件验收，而不是生产已验证。
