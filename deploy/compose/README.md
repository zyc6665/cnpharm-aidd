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

## 上线前必须注入的 SSO 配置

统一身份认证（IAM SSO）的 16 个 `SSO_*` 键已逐项写进 `docker-compose.prod.yml` 的
`environment: &app_environment` 锚点（`api` 定义内，第 54 行起），`api` 与四个
`celery-*` / worker 服务都通过 `<<: *app_environment` 继承，只在一处维护。
每项都带默认值，`SSO_ENABLED=false`（默认）时整块留空也能通过 `config` 校验。

| 变量 | 默认 | 说明 |
|---|---|---|
| `SSO_ENABLED` | `false` | 总开关。关闭时其余项留空即可 |
| `SSO_AUTO_PROVISION` | **`false`** | 首次登录是否自动开户。**开启前必须确认甲方应用可见范围** |
| `SSO_ALLOWED_UNIT_CODES` | 空 | 准入白名单（逗号分隔的甲方 `unitCode`，空=不限制，≤64 项、单项 ≤64 字符、大小写敏感） |
| `SSO_BASE_URL` | 空 | 甲方 IAM 地址 |
| `SSO_APP_ID` | 空 | 甲方分配的 appId |
| `SSO_CLIENT_SECRET` | 空 | 甲方分配的 clientSecret（**敏感**，走 secret 注入） |
| `SSO_REDIRECT_URI` | 空 | 回调地址 |
| `SSO_SUCCESS_PATH` | `/workspace` | 登录成功后前端落地路由 |
| `SSO_DEFAULT_ROLE` | `user` | 自动开户的初始角色 |
| `SSO_USERNAME_CLAIM` | `userName` | 用 IAM 哪个字段当用户名 |
| `SSO_VALIDATE_ON_REFRESH` | `true` | 续期时是否回源校验 |
| `SSO_TIMEOUT_SECONDS` | `5` | 调 IAM 的超时 |
| `SSO_TLS_VALIDATE` | `true` | 校验 IAM 证书；内网自签需换信任根，**不要**改成 false |
| `SSO_STATE_TTL_SECONDS` | `300` | 授权态 Cookie 有效期 |
| `SSO_OFFLINE_GRACE_SECONDS` | `86400` | IAM 不可达时的离线宽限；0 = 严格失败关闭 |
| `SSO_LOGOUT_REDIRECT_URI` | 空 | IAM 主动登出时允许的回跳地址 |

五条口径：

1. **白名单对所有 SSO 登录生效，不只自动开户**——只挡新开户的话，已开户的人换个
   `unitCode` 照样进得来。判定发生在任何写入之前，且续期不回传 `orgs`，所以它是
   **准入闸**而非实时吊销：调岗后要等下一次重新登录才生效。
2. **`sso_uid` 清空 ≠ 吊销**。管理端解绑只是解除绑定关系，同一 IAM 用户下次登录仍会按用户名自动重新绑定；
   要真正挡住某人，请停用账号（`status=disabled`）。
3. **`SSO_AUTO_PROVISION` 默认关**。甲方应用可见范围往往比平台开放范围大，默认开等于
   把范围判定交给甲方配置。开启前请确认可见范围，必要时配 `SSO_ALLOWED_UNIT_CODES`。
4. **`SSO_CLIENT_SECRET` 只走 secret 管理**，不要写进 compose 文件或 `.env` 提交。
5. **不要在 SSO 段写公网地址**：`SSO_BASE_URL` / `SSO_REDIRECT_URI` /
   `SSO_LOGOUT_REDIRECT_URI` 只允许内网或集群内地址，CI 的离线合规扫描会拦。

改完配置先自检（`config` 会校验 8 个必填变量）：

```sh
export CORS_ORIGINS=https://aidd.example.internal
export JWT_SECRET_KEY=$(openssl rand -hex 24)
export SETTINGS_ENCRYPTION_KEY=$(openssl rand -hex 24)
export POSTGRES_PASSWORD=dev-only
export REDIS_PASSWORD=dev-only
export MINIO_ROOT_USER=dev-only
export MINIO_ROOT_PASSWORD=dev-only
export MINIO_CERTS_DIR=/etc/minio/certs
docker compose -f deploy/compose/docker-compose.prod.yml config >/dev/null
```
