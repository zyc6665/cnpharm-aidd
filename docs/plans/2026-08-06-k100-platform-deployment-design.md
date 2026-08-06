# K100 Platform Deployment Test Design

## 背景

K100/DCU 模型兼容性测试已经确认四个模型 CPU smoke 通过、DCU 加速暂未通过。下一阶段需要把平台侧部署到信创测试机，验证平台自身的服务编排、任务中心、日志、Artifact、Workflow 和模型执行链路。

## 部署原则

平台侧测试采用 Docker Compose 单机编排，而不是直接拷源码启动。Compose 更接近后续 K8s 拆分形态：后端、Worker、前端、数据库、Redis、MinIO 各自独立，生命周期清晰，排障简单。

模型运行环境不打进平台镜像。模型继续作为独立 runtime/package，由平台 Worker 通过现有执行 Interface 调用远端或本机 `model_test` 容器。平台只依赖标准任务输入目录、输出目录、`platform_run.sh`、`result.json`、日志和 Artifact，不根据模型实现写分支。

## 模块 Interface

### 平台运行 Interface

- 后端镜像提供 FastAPI、Alembic、Celery 代码。
- Worker 复用后端镜像，只更换启动命令。
- 前端镜像只提供静态资源和 nginx 反向代理。
- Postgres、Redis、MinIO 作为测试基础设施，不嵌入应用镜像。

### 模型执行 Interface

- 第一阶段继续使用 `ssh_job` 执行器。
- 若平台和 `model_test` 在同一台机器，可通过 SSH 到宿主机后 `docker exec model_test`。
- 不在平台镜像中安装 DGL、TensorFlow、PyG 或模型权重。

## 测试目标

1. Compose 能启动 backend、worker、frontend、postgres、redis、minio。
2. Alembic 能在容器内执行 `upgrade head`。
3. 前端能通过 `/api/v1` 访问后端，并支持 WebSocket 转发。
4. 平台能登录、创建项目、上传文件、发起任务。
5. Worker 能调用 K100 测试机上的 CPU smoke 模型包。
6. 任务中心能显示状态、日志、进度消息和 Artifact。

## 非目标

- 不在本阶段迁移到完整 K8s。
- 不把模型环境合并进平台镜像。
- 不把 DCU 加速作为平台部署通过条件。
- 不提交真实 `.env`、私钥、密码或商业测试机凭据。

