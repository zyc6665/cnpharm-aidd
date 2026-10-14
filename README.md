# 科学计算工具管理平台

科学计算工具管理平台是一个面向科研计算场景的工具托管、任务执行、文件管理和工作流编排平台。

平台的长期执行模型是：**管理员注册工具和模型镜像，平台根据工具版本的执行契约调度任务，最终由 Kubernetes Job 承载模型运行**。当前仍保留 SSH 工具版本和 `direct` 开发执行模式，用于兼容已有工具和本地联调。

## 当前基线

当前日常开发分支是 `develop`。`main` 用于稳定版本，`beta` 用于预发布验收；历史版本分支仅用于归档或维护，不作为新功能默认入口。

当前实现处于 Kubernetes 调度渐进迁移阶段：

- 普通用户只能使用已经发布并允许执行的工具版本。
- 模型和工具由管理员注册，用户不上传或注册模型。
- 新模型优先使用管理员 Tool Package v2 注册流程。
- 同一个工具可以暂时同时保留 SSH 版本和 Kubernetes 版本；新增 Kubernetes 候选版本不会自动修改正在使用的 SSH 版本。
- 模型镜像由模型维护人员或管理员在平台外构建、导出或推送，平台负责登记、校验、导入和使用镜像引用，不负责模型内部适配。
- 生产 Kubernetes 运行需要固定镜像 digest、可用的 Registry、MinIO、PostgreSQL、Redis、RBAC 和执行 Worker。

> 当前工作树可能包含尚未提交的开发进度。新服务器只能从远端已提交的内容恢复；在迁移前请先按[远端迁移清单](#迁移到另一台服务器)整理、检查并推送当前应保留的改动。

## 功能范围

- **工具管理**：工具、工具版本、Tool Package v2、输入输出契约和管理员注册。
- **任务执行**：保留 SSH 执行，逐步接入 Kubernetes Job；本地开发支持 `direct` 进程内执行。
- **资源管理**：CPU/GPU Resource Profile、资源快照、执行约束和任务资源校验。
- **文件与 Artifact**：本地文件存储或 MinIO 对象存储，支持输入、输出、校验和下载。
- **工作流**：工作流定义、节点运行和结果关联，后续统一投影到 Run/Attempt 模型。
- **平台管理**：管理员工具注册、候选版本 Smoke、版本提升和回滚。
- **基础设施**：提供 PostgreSQL、Redis、MinIO、私有 Registry 和 Kubernetes Worker 的部署模板。

## 技术栈与运行模式

| 组件 | 本地开发 | 预发布/生产 |
| --- | --- | --- |
| 后端 | FastAPI + Uvicorn | FastAPI 容器 |
| 数据库 | SQLite | PostgreSQL |
| 缓存 | 内存 | Redis |
| 任务执行 | `direct` | Celery + Redis，或后续统一调度 Worker |
| 文件存储 | 本地目录 | MinIO |
| 模型执行 | SSH 或本地联调 | Kubernetes Job |
| 镜像 | 本地构建或导入 | Registry 中的固定 digest |
| 前端 | Vue 3 + Vite | Vite 构建产物或前端容器 |

`direct` 只适合开发和短任务联调。它不提供跨进程恢复、可靠排队和多实例一致性；长时间任务、工作流和正式环境应使用 Celery 或 Kubernetes 调度链路。

## 项目结构

```text
cpumodel_sciminer/
├── backend/                         # FastAPI 后端、数据库、执行器和迁移
│   ├── app/
│   │   ├── api/v1/                  # REST API
│   │   ├── execution/               # 执行契约、SSH/Kubernetes transport
│   │   ├── models/                  # SQLAlchemy 模型
│   │   ├── services/                # 任务、工具、运行准备等领域服务
│   │   ├── tasks/                   # 任务服务、资源档位和执行器
│   │   ├── tool_packages/           # Tool Package、digest 和 K8s 注册
│   │   ├── storage/                 # local/MinIO 存储适配器
│   │   └── worker/                  # Celery 应用和 Worker 任务
│   ├── alembic/                     # 数据库迁移
│   ├── requirements.txt             # 运行依赖
│   ├── requirements-dev.txt         # 测试和开发依赖
│   └── .env.example                 # 配置模板，不含真实凭据
├── frontend/                        # Vue 3 + Vite 前端
│   ├── src/api/                     # API 客户端
│   ├── src/domain/                  # 领域类型和纯函数
│   ├── src/views/                   # 页面
│   ├── test/                        # Vitest 测试
│   └── package-lock.json             # 前端依赖锁定文件
├── test/                            # 后端 pytest 测试
├── deploy/
│   ├── compose/                     # 本地/生产 Compose 模板
│   └── kubernetes/                  # K3s/Kubernetes 基础设施和 Worker 模板
├── example/                         # 工具包、模型运行时和输入输出示例
├── docs/
│   ├── architecture/                # 架构说明
│   ├── development/                 # 团队协作和仓库规范
│   ├── guides/                      # 开发、工具和部署指南
│   ├── plans/                       # 设计与实施计划
│   └── product/                     # 产品和验收文档
├── scripts/                         # 开发辅助脚本和迁移脚本
├── alembic.ini                      # Alembic 入口配置
├── .gitignore                       # 本地环境、运行数据和模型文件边界
└── README.md                        # 项目入口和开发接续手册
```

## 迁移到另一台服务器

### 1. 迁移前必须确认

当前工作树中的未提交代码不会随着 `git clone` 自动迁移。迁移前应在旧服务器完成以下工作：

1. 查看 `git status`，确认要保留的后端、前端、测试、部署配置和文档改动。
2. 检查新加入文件，尤其是 Tool Package、Kubernetes 注册逻辑、迁移文件和测试文件。
3. 检查 `.env`、数据库、日志、模型目录和镜像导出文件没有进入 Git。
4. 运行后端重点测试、前端测试和构建。
5. 对改动进行代码审查后提交到 `develop`，再推送远端。

本次应纳入远端评估的内容包括：

- 后端工具包注册、Kubernetes 绑定、任务资源配置和数据库迁移。
- 前端管理员工具包注册页面、API、类型、路由和相关测试。
- Kubernetes 基础设施、Worker、Registry、MinIO 和模型镜像模板。
- 工具创建指南、模型运行时规范、部署说明、设计文档和实施计划。
- 与这些功能对应的后端 pytest、前端 Vitest 和契约测试。

明确不应推送：

- `backend/.env`、本地数据库、日志、上传文件和 `backend/storage/` 运行数据。
- `frontend/node_modules/`、构建产物和本机专用环境配置。
- `model/`、`model-build/` 中的模型包、权重、数据集和缓存。
- `docker save` 导出文件、临时镜像上下文、私有密钥、访问令牌和服务器凭据。

模型仓库不属于平台代码仓库。平台仓库只保留通用模型镜像模板、运行时契约、示例和 Kubernetes 部署配置。

### 2. 新服务器克隆

```bash
git clone --branch develop --single-branch <仓库地址> cpumodel_sciminer
cd cpumodel_sciminer
git status --short --branch
```

不要直接从 `main` 开始开发，也不要把旧服务器的 `.env`、SQLite 数据库或模型目录复制进 Git 工作树。若远端尚未包含旧服务器的最新提交，应先完成旧服务器的提交和推送，再执行克隆。

### 3. 安装后端依赖

推荐使用 Python 3.11，并为项目单独创建虚拟环境：

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
cp .env.example .env
mkdir -p storage
cd ..
```

新服务器的 `backend/.env` 需要单独配置。开发环境可以使用 SQLite、本地文件存储、内存缓存和 `direct`；不要把旧服务器的生产凭据、数据库密码、MinIO 密钥或 Kubernetes Token 写入 README 或提交到仓库。

### 4. 初始化开发数据库

开发环境启动时会对缺失表执行 `create_all` 兜底，但涉及结构变更时仍必须使用 Alembic：

```bash
source backend/.venv/bin/activate
alembic -c alembic.ini upgrade head
```

如果使用 PostgreSQL、MinIO 或 Redis，应先配置对应服务地址和凭据，再执行迁移。生产和预发布环境禁止依赖开发模式的自动建表兜底。

### 5. 启动后端

```bash
source backend/.venv/bin/activate
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

常用地址：

- API 文档：`http://localhost:8000/docs`
- 存活检查：`http://localhost:8000/health`
- 系统健康检查：`http://localhost:8000/api/v1/system/health`

### 6. 安装并启动前端

```bash
cd frontend
npm ci
npm run dev -- --host 0.0.0.0 --port 8585
```

Vite 配置默认端口是 `3000`；需要保持当前演示环境的 `8585` 端口时，使用上面的显式参数或在新服务器的本地启动脚本中固定端口。前端 API 地址必须指向后端 `8000` 端口，WebSocket 地址也必须与后端端口一致。

## 配置与凭据边界

后端配置模板位于 `backend/.env.example`，重点配置项如下：

| 配置 | 本地开发 | Kubernetes/生产 |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `staging` 或 `production` |
| `DATABASE_URL` | SQLite | PostgreSQL |
| `STORAGE_BACKEND` | `local` | `minio` |
| `CACHE_BACKEND` | `memory` | `redis` |
| `TASK_EXECUTION_BACKEND` | `direct` | `celery` |
| `EXECUTOR_ENABLED_K8S` | 默认关闭 | 基础设施验收后开启 |
| `EXECUTOR_ENABLED_SSH` | 按现有工具需要开启 | 兼容期继续保留 |
| `IMAGE_REGISTRY_*` | 可不配置 | 管理员镜像导入和校验 |

配置原则：

- `.env` 只存在于具体部署环境，不通过 Git 在服务器之间迁移。
- 生产和预发布必须使用独立的 JWT、配置加密、数据库、Redis、MinIO 和 Registry 凭据。
- Kubernetes 凭据、Namespace、ServiceAccount 和对象存储 Secret 由 Worker 部署环境绑定，不写入用户提交的 ToolVersion 参数。
- 工具版本中的镜像必须使用不可变 digest；tag 只能用于开发阶段，不作为生产发布身份。

## 工具与模型注册流程

新模型的职责边界是“模型侧适配，平台侧注册和调度”：

1. 模型维护人员按照 `docs/guides/model-runtime-packaging.md` 和 `deploy/kubernetes/model-image-template/` 准备标准模型镜像。
2. 镜像至少包含 `model/`、`platform_adaptor/`、运行说明和 `MODEL_PACKAGE.yaml`，并提供参数、输入、输出和 `result.v2` 契约。
3. 模型维护人员在平台外构建镜像并推送到管理员可访问的 Registry，或导出镜像文件交给管理员导入。
4. 管理员在前端 Tool Package 页面导入、校验并发布 Tool Package v2。
5. 管理员从已发布包中选择 Kubernetes variant 和平台允许的 Resource Profile，创建候选 ToolVersion。
6. 管理员提供 Smoke 输入并执行真实验证；候选版本只有在 Smoke 成功且基础设施就绪后才允许提升。
7. 提升后新任务才可以选择该版本；旧 SSH 版本继续保留，必要时可以回滚。

普通用户不参与模型注册，也不能通过任务请求绕过版本状态、工具归属、镜像 digest 或资源档位校验。旧工具仍按原有兼容路径运行，直到完成真实使用迁移和回归验收。

详细说明：

- 工具创建和管理员注册：`docs/guides/CREATE_TOOL_GUIDE.md`
- 模型运行时规范：`docs/guides/model-runtime-packaging.md`
- 通用镜像模板：`deploy/kubernetes/model-image-template/README.md`
- Kubernetes 注册设计：`docs/plans/2026-10-10-admin-k8s-tool-registration-design.md`
- Kubernetes 注册实施计划：`docs/plans/2026-10-10-admin-k8s-tool-registration.md`

## Kubernetes 与基础设施

Kubernetes 开发环境模板位于 `deploy/kubernetes/`，包括：

- 单节点 K3s 命名空间和基础资源。
- PostgreSQL、Redis、MinIO 和私有 OCI Registry。
- 模型 Job 的 RBAC、ServiceAccount 和对象存储 Secret 模板。
- 可选的 Celery 执行 Worker 模板。
- Registry、MinIO、模型镜像和 smoke 测试说明。

基础设施部署顺序和安全要求以 `deploy/kubernetes/README.md` 为准。启用 Kubernetes 执行前，必须依次确认：

1. Worker 能访问 Kubernetes API。
2. 目标节点能拉取固定 digest 镜像。
3. Model Job 的 ServiceAccount 只有所需的最小权限。
4. MinIO bucket、输入输出前缀和客户端 Secret 可用。
5. Registry、PostgreSQL、Redis 和 MinIO 的持久卷状态正常。
6. 单个 GPU `k8s_job` 工具完成真实 Smoke 和结果回收。

`direct` 后端可以用于本地直接调用执行适配器，但它不能替代正式 Worker 的断线恢复、排队和重试能力。后端和 Worker 可以部署在不同机器或不同 Kubernetes Pod 中，只要共享数据库、Redis、对象存储和 Kubernetes 执行权限。

## 后续开发顺序

新服务器拉取仓库后，按下面顺序继续，不要直接进行全局重命名或大规模页面改造：

### 阶段 0：冻结基线（M0）

先完成以下清点并形成可审查记录：

1. 工具、Tool Package、ToolVersion、SSH/Kubernetes variant 和镜像 digest 的命名注册表。
2. `Task`、`WorkflowRun`、Artifact、执行记录和外部 Job 的真实状态链路。
3. 新旧 `Task` 与目标 `Run/RunAttempt/RunEvent/DispatchOutbox` 的字段映射。
4. 一个固定 GPU `k8s_job` 试点工具和完整输入输出样例。
5. 当前前端工作台、运行详情和工具目录的视觉验收页面。

M0 未通过前，不执行仓库目录重命名、批量 Kubernetes 资源重命名、全局品牌字符串替换或生产 Feature Flag 切换。

### 阶段 1：统一运行底座（M1–M3）

1. 增加 Run、RunAttempt、RunEvent、DispatchOutbox 数据模型和迁移。
2. 定义可持久化状态机、失败分类、取消语义、重试预算和幂等键。
3. 将现有 direct、Celery、SSH 和 Kubernetes 执行路径收敛到统一执行契约。
4. 增加 Scheduler、Reconciler、Outbox publisher 和 Job 状态回收测试。
5. 为重复提交、Worker 重启、Job 创建冲突、Redis 短暂不可用和结果校验失败补充测试。

### 阶段 2：运行中心和项目工作台（M4–M5）

1. 后端提供 `/runs` 列表、详情、事件、日志、Attempt 和 Artifact 查询契约。
2. 前端增加项目上下文、运行中心、运行详情和失败下一步提示。
3. 通过 domain 层兼容旧 `Task`/`WorkflowRun`，页面不直接绑定旧数据库字段。
4. 完成桌面、平板、移动端、加载态、空态、错误态和权限态验收。

### 阶段 3：真实集群闭环（M6）

1. 完成 Registry、MinIO、GPU 节点、Device Plugin、RBAC 和 Worker readiness 检查。
2. 使用固定 digest 的试点模型完成输入上传、Job 创建、日志、输出回收和结果展示。
3. 验证取消、重试、Worker 重启、节点不可用和结果校验失败。
4. 形成真实集群验收记录后，再决定是否扩大 Kubernetes 工具版本的发布范围。

### 阶段 4：生产强化和旧路径退役（M7–M8）

在 M6 真实闭环稳定后，再推进监控、容量、灰度、回滚和旧 SSH/direct 路径退役。任何旧路径的删除都必须以使用盘点、兼容迁移、回归测试和可回滚版本为前提。

关联计划：

- `docs/plans/2026-10-13-aiphamedx-scheduling-and-workspace-implementation.md`
- `docs/plans/2026-10-13-cpumodel-scheduling-and-workspace-redesign.md`
- `docs/plans/2026-10-03-k8s-platform-foundation.md`
- `docs/dev/AIPhaMedX_Computing_Scheduling_Design.md`

## 验证清单

新服务器接续开发后，至少完成以下验证：

```bash
# 后端测试
source backend/.venv/bin/activate
pytest -q

# 前端单元测试和生产构建
cd frontend
npm test
npm run build
cd ..

# 数据库迁移检查
alembic -c alembic.ini upgrade head
```

功能开发完成后还需要按改动范围补充验证：

- 工具注册、版本状态、digest 校验和管理员权限。
- 旧 SSH 工具的直接执行回归。
- Kubernetes 候选版本的资源档位、Smoke、promotion 和回滚。
- 输入 Artifact、输出 Artifact、checksum、权限和下载链路。
- Workflow 入口、节点执行、运行状态和错误展示。
- PostgreSQL、Redis、MinIO、Registry、Worker 和 GPU 节点的集群验收。

## 文档导航

- 团队协作规范：`docs/development/01-团队协作开发规范与教程.md`
- 开发指南：`docs/guides/DEVELOPMENT.md`
- 快速启动：`docs/guides/QUICKSTART.md`
- Kubernetes 部署：`deploy/kubernetes/README.md`
- Celery 部署：`docs/guides/CELERY_DEPLOYMENT.md`
- 工具创建：`docs/guides/CREATE_TOOL_GUIDE.md`
- 模型运行时：`docs/guides/model-runtime-packaging.md`
- 产品需求：`docs/product/01-平台需求说明书.md`
- 平台功能：`docs/product/02-平台功能模块说明书.md`
- 验收场景：`docs/product/03-验收流程与测试场景.md`

## 许可证

本项目使用 MIT License，详见 `LICENSE`。
