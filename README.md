# 科学计算工具管理平台
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-teal.svg)](https://fastapi.tiangolo.com/)
[![Vue3](https://img.shields.io/badge/Vue-3.x-brightgreen.svg)](https://vuejs.org/)

## 📖 项目简介

科学计算工具管理平台是一个通用的科学计算任务调度和管理系统，旨在为科研人员提供便捷的算法工具托管、任务提交、GPU资源调度和结果管理服务。

### 核心特性

- 🚀 **工具托管**：支持远程API、Docker镜像、Python脚本等多种工具接入方式
- 🎯 **任务调度**：基于Celery的分布式任务队列，支持优先级和多队列
- 💻 **GPU管理**：智能GPU资源分配，支持多节点、多卡调度
- 🧬 **工作流与智能体**：契约驱动的工具编排与 AIDD 规划能力
- 📊 **实时监控**：WebSocket实时推送任务进度
- 💾 **文件管理**：支持本地存储和MinIO对象存储，SHA256去重
- 🔒 **安全认证**：JWT认证，RBAC权限控制

### ⚡ 开发模式特性

支持**轻量化开发模式**，无需 Docker/PostgreSQL/Redis/MinIO 即可运行：

| 组件 | 开发模式 | 生产模式 |
|------|----------|----------|
| 数据库 | SQLite | PostgreSQL |
| 文件存储 | 本地文件系统 | MinIO (S3) |
| 缓存 | 内存缓存 | Redis |
| 任务队列 | direct 进程内执行（仅开发调试） | Celery + Redis |

> 工作流、Agent 和 ssh_job 这类长时任务在生产环境应使用 `Celery + Redis`。`direct` 模式仅用于本地开发联调，进程重启、热更新或单进程阻塞都会直接影响任务连续性。

---

## 🏗️ 技术架构

### 后端技术栈

- **Web框架**：FastAPI 0.109+
- **ORM**：SQLAlchemy 2.0 (异步)
- **数据库**：SQLite (开发) / PostgreSQL (生产)
- **缓存**：内存 (开发) / Redis (生产)
- **任务队列**：同步 (开发) / Celery (生产)
- **对象存储**：本地 (开发) / MinIO (生产)

### 前端技术栈

- **框架**：Vue 3 + Vite
- **状态管理**：Pinia
- **UI组件**：Ant Design Vue
- **图表**：ECharts

### 当前开发约定

- 当前过渡基线分支：`v1.0-7.28`
- 当前工作目录：`/data/zhouyc/cpumodel_sciminer`
- 团队协作、分支、PR、合并和发布流程以 `docs/development/01-团队协作开发规范与教程.md` 为准。
- 后续新开发应逐步过渡到 `main`、`beta`、`develop` 三层长期分支模型；过渡完成前，不建议继续把新功能直接合入稳定或历史版本分支。

### 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                          用户层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Web浏览器   │  │  移动端APP   │  │  API客户端   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTPS
┌─────────────────────┴───────────────────────────────────────┐
│                     应用层 (FastAPI)                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │认证授权  │ │工具管理  │ │任务调度  │ │文件服务  │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────────┐
│                    适配层 (可切换后端)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │存储适配器    │  │ 缓存适配器   │  │ 任务适配器   │      │
│  │local/minio   │  │memory/redis  │  │sync/celery   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────────┐
│                        数据层                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │SQLite/PgSQL  │  │ Memory/Redis │  │ Local/MinIO  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

---

## 📂 项目结构

```
cpumodel_sciminer/
├── docs/                       # 文档目录
│   ├── design/                 # 设计文档
│   │   ├── 01-总体设计说明书.md
│   │   ├── 02-数据库设计说明书.md
│   │   ├── 03-接口规格说明书.md
│   │   └── 04-详细设计说明书.md
│   └── sql/                    # SQL脚本
│
├── backend/                    # 后端代码
│   ├── app/
│   │   ├── api/v1/             # API路由
│   │   │   ├── auth.py         # 认证接口
│   │   │   ├── tools.py        # 工具管理
│   │   │   ├── tasks.py        # 任务管理
│   │   │   └── files.py        # 文件管理
│   │   ├── models/             # ORM模型
│   │   │   ├── users.py
│   │   │   ├── tools.py
│   │   │   ├── tasks.py
│   │   │   └── files.py
│   │   ├── schemas/            # Pydantic Schema
│   │   ├── auth/               # 认证授权
│   │   │   ├── jwt_handler.py
│   │   │   ├── password.py
│   │   │   └── dependencies.py
│   │   ├── storage/            # 存储适配层 ⭐
│   │   │   ├── base.py         # 抽象基类
│   │   │   ├── local.py        # 本地存储
│   │   │   ├── minio_backend.py # MinIO存储
│   │   │   └── factory.py      # 工厂函数
│   │   ├── cache/              # 缓存适配层 ⭐
│   │   │   ├── base.py         # 抽象基类
│   │   │   ├── memory.py       # 内存缓存
│   │   │   ├── redis_backend.py # Redis缓存
│   │   │   └── factory.py      # 工厂函数
│   │   ├── worker/             # Celery任务 ⭐
│   │   │   ├── celery_app.py   # Celery配置
│   │   │   └── tasks.py        # 异步任务
│   │   ├── database/           # 数据库
│   │   │   ├── base.py
│   │   │   └── session.py
│   │   ├── common/             # 通用工具
│   │   ├── config.py           # 配置管理
│   │   └── main.py             # FastAPI入口
│   ├── storage/                # 数据存储目录
│   ├── requirements.txt        # 生产 Python 依赖
│   ├── requirements-dev.txt    # 开发、测试与本地监控依赖
│   ├── .env                    # 环境配置
│   └── .env.example            # 环境配置示例
│
├── frontend/                   # Vue 3 前端
│   ├── src/                    # 页面、组件、状态和 API 客户端
│   └── test/                   # Vitest 前端测试
├── test/                       # 后端 pytest 测试
├── .github/workflows/          # CI 工作流
├── docker-compose.yml          # 开发环境 Compose
├── docker-compose.celery.yml   # Redis、Celery 与 Flower Compose
├── docker-compose.prod.yml     # PostgreSQL、Redis、MinIO 与多 Worker 生产 Compose
└── README.md                   # 本文件
```

---

## 🚀 快速开始

### 开发模式（推荐新手）

无需 Docker，直接使用 SQLite + 本地存储：

```bash
# 1. 进入后端目录
cd backend

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 安装开发依赖（包含生产依赖、pytest、flake8、watchfiles）
pip install -r requirements-dev.txt

# 4. 复制配置文件（使用默认开发配置）
cp .env.example .env

# 5. 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问：
- **API文档**：http://localhost:8000/docs
- **存活检查**：http://localhost:8000/health
- **系统健康检查**：http://localhost:8000/api/v1/system/health

### 生产模式

生产部署使用 `docker-compose.prod.yml`，包含 PostgreSQL、Redis、MinIO、后端服务和多 Celery Worker。启动前先在 shell 或部署平台中设置必要密钥：

```env
# 环境
ENVIRONMENT=production
DEBUG=false

POSTGRES_PASSWORD=change-me
REDIS_PASSWORD=change-me
MINIO_ROOT_USER=scitool
MINIO_ROOT_PASSWORD=change-me
JWT_SECRET_KEY=change-me-with-at-least-32-characters
SETTINGS_ENCRYPTION_KEY=change-me-with-at-least-32-characters
CORS_ORIGINS=["https://your-domain.example"]
```

启动生产服务：

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

如需 GPU Worker，额外启用 Compose profile：`docker compose -f docker-compose.prod.yml --profile gpu up -d --build`。

---

## 🔧 配置说明

### 环境变量一览

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ENVIRONMENT` | development | 环境：development/staging/production |
| `DEBUG` | true | 调试模式 |
| `DATABASE_URL` | sqlite+aiosqlite:///./storage/scitool.db | 数据库连接 |
| `JWT_SECRET_KEY` | your-secret-key... | JWT密钥（生产环境必须修改） |
| `STORAGE_BACKEND` | local | 存储后端：local/minio |
| `STORAGE_PATH` | ./storage/uploads | 本地存储路径 |
| `CACHE_BACKEND` | memory | 缓存后端：memory/redis |
| `REDIS_URL` | redis://localhost:6379/0 | Redis连接 |
| `CELERY_BROKER_URL` | (空) | Celery消息代理；`TASK_EXECUTION_BACKEND=celery` 且未配置时会回退到 `direct` |
| `TASK_EXECUTION_BACKEND` | celery | `celery` 或 `direct`，`direct` 仅建议开发使用 |
| `WORKFLOW_RECONCILE_INTERVAL_SECONDS` | 5 | 工作流后台对账轮询间隔（秒） |
| `WORKFLOW_RECONCILE_BATCH_SIZE` | 20 | 单次工作流对账最大处理数 |
| `MAX_FILE_SIZE_MB` | 100 | 最大文件大小(MB) |

完整配置示例见 `backend/.env.example`

---

## 📚 API接口

### 认证接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/auth/register | 用户注册 |
| POST | /api/v1/auth/login | 用户登录 |
| POST | /api/v1/auth/refresh | 刷新令牌 |
| GET | /api/v1/auth/me | 获取当前用户 |
| PUT | /api/v1/auth/me | 更新用户信息 |
| POST | /api/v1/auth/change-password | 修改密码 |

### 工具接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/tools | 获取工具列表 |
| GET | /api/v1/tools/{id} | 获取工具详情 |
| POST | /api/v1/tools | 创建工具(管理员) |
| PUT | /api/v1/tools/{id} | 更新工具(管理员) |
| DELETE | /api/v1/tools/{id} | 删除工具(管理员) |
| POST | /api/v1/tools/{id}/favorite | 收藏工具 |
| GET | /api/v1/tools/{id}/versions | 获取版本列表 |

### 任务接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/tasks | 获取任务列表 |
| GET | /api/v1/tasks/{id} | 获取任务详情 |
| POST | /api/v1/tasks | 创建任务 |
| POST | /api/v1/tasks/{id}/cancel | 取消任务 |
| POST | /api/v1/tasks/{id}/retry | 重试任务 |
| GET | /api/v1/tasks/{id}/logs | 获取任务日志 |

### 文件接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/files/upload | 上传文件 |
| GET | /api/v1/files | 获取文件列表 |
| GET | /api/v1/files/{id} | 获取文件信息 |
| GET | /api/v1/files/{id}/download | 下载文件 |
| DELETE | /api/v1/files/{id} | 删除文件 |
| POST | /api/v1/files/batch-delete | 批量删除 |

---

## 🛠️ 适配层使用

### 存储适配器

```python
from app.storage import get_storage_backend

# 自动根据配置选择后端
storage = get_storage_backend()

# 上传文件
result = await storage.upload(file_data, "path/to/file.txt")

# 下载文件
data = await storage.download("path/to/file.txt")

# 获取预签名URL（MinIO）或API路径（本地）
url = await storage.get_url("path/to/file.txt", expires_in=3600)

# 删除文件
await storage.delete("path/to/file.txt")
```

### 缓存适配器

```python
from app.cache import get_cache_backend

cache = get_cache_backend()

# 基本操作
await cache.set("key", "value", expire=3600)
value = await cache.get("key")
await cache.delete("key")

# JSON 操作
await cache.set_json("user:1", {"name": "张三", "age": 30})
user = await cache.get_json("user:1")

# 计数器
count = await cache.incr("page_views")
```

### 任务执行

```python
from app.tasks.service import create_and_schedule_tool_task

# 统一通过任务创建服务调度
# 开发模式：根据配置走 direct 进程内执行
# 生产模式：根据配置走 Celery + Redis 异步执行
```

对于需要跨进程恢复、长时间排队或多用户并发的真实药研工作流，不要依赖 `direct` 模式。

---

## 📊 开发进度

### 已完成 ✅

- [x] 项目结构搭建
- [x] 配置管理（支持多环境）
- [x] 数据库层（SQLAlchemy 异步）
- [x] ORM模型（用户、工具、任务、文件）
- [x] JWT认证授权
- [x] 认证API
- [x] 工具管理API
- [x] 任务管理API
- [x] 文件管理API
- [x] 存储适配层（本地/MinIO）
- [x] 缓存适配层（内存/Redis）
- [x] Celery任务队列配置
- [x] Vue 3 前端工作台与管理后台
- [x] WebSocket实时推送
- [x] GPU资源管理与队列路由
- [x] Docker 开发/生产部署配置
- [x] CI 后端测试、前端测试、生产 Compose 校验

### 持续完善 🔄

- [ ] 端到端测试覆盖
- [ ] 生产监控告警策略
- [ ] Agent 辅助生成工作流草稿与更完整的商业化能力闭环

---

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源许可证。

---

## 📞 联系方式

- **问题反馈**：https://github.com/your-org/cpumodel_sciminer/issues

---

**版本**：1.0.0-MVP
**最后更新**：2026-07-29
