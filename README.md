# 科学计算工具管理平台

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-teal.svg)](https://fastapi.tiangolo.com/)
[![Vue3](https://img.shields.io/badge/Vue-3.x-brightgreen.svg)](https://vuejs.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-blue.svg)](https://www.postgresql.org/)

## 📖 项目简介

科学计算工具管理平台是一个通用的科学计算任务调度和管理系统，旨在为科研人员提供便捷的算法工具托管、任务提交、GPU资源调度和结果管理服务。

### 核心特性

- 🚀 **工具托管**：支持远程API、Docker镜像、Python脚本等多种工具接入方式
- 🎯 **任务调度**：基于Celery的分布式任务队列，支持优先级和多队列
- 💻 **GPU管理**：智能GPU资源分配，支持多节点、多卡调度
- 👥 **游客模式**：无需注册即可体验核心功能
- 📊 **实时监控**：WebSocket实时推送任务进度，Prometheus+Grafana监控
- 💾 **文件管理**：MinIO对象存储，SHA256去重，生命周期管理
- 🔒 **安全认证**：JWT认证，RBAC权限控制，敏感信息脱敏

---

## 🏗️ 技术架构

### 后端技术栈

- **Web框架**：FastAPI 0.109+
- **ORM**：SQLAlchemy 2.0 (异步)
- **数据库**：PostgreSQL 15+
- **缓存**：Redis 7.0+
- **任务队列**：Celery 5.3+
- **对象存储**：MinIO (S3兼容)
- **监控**：Prometheus + Grafana
- **部署**：Docker + Docker Compose

### 前端技术栈

- **框架**：Vue 3 + Vite
- **状态管理**：Pinia
- **UI组件**：Element Plus
- **图表**：ECharts
- **3D可视化**：NGL Viewer

### 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                          用户层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  Web浏览器   │  │  移动端APP   │  │  API客户端   │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTPS
┌─────────────────────┴───────────────────────────────────────┐
│                        前端层 (Vue3)                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │
│  │工具广场  │ │任务管理  │ │结果可视  │ │系统监控  │     │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘     │
└─────────────────────┬───────────────────────────────────────┘
                      │ REST API + WebSocket
┌─────────────────────┴───────────────────────────────────────┐
│                     应用层 (FastAPI)                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │
│  │认证授权  │ │工具管理  │ │任务调度  │ │文件服务  │     │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                   │
│  │GPU资源   │ │监控告警  │ │日志管理  │                   │
│  └──────────┘ └──────────┘ └──────────┘                   │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────────┐
│                    任务队列 (Celery)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │高优先级队列  │  │ GPU任务队列  │  │ CPU任务队列  │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────────┐
│                        数据层                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ PostgreSQL   │  │    Redis     │  │    MinIO     │    │
│  │   (主库)     │  │  (缓存+队列) │  │  (对象存储)  │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
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
│       ├── 001_schema.sql      # 数据库Schema
│       └── 002_seed.sql        # 种子数据
│
├── backend/                    # 后端代码
│   ├── app/
│   │   ├── api/                # API路由
│   │   │   ├── auth.py         # 认证接口
│   │   │   ├── tools.py        # 工具管理
│   │   │   ├── tasks.py        # 任务管理
│   │   │   ├── files.py        # 文件管理
│   │   │   └── gpu.py          # GPU资源
│   │   ├── models/             # 数据库模型
│   │   │   ├── users.py
│   │   │   ├── tools.py
│   │   │   ├── tasks.py
│   │   │   ├── files.py
│   │   │   └── gpu.py
│   │   ├── schemas/            # Pydantic Schema
│   │   ├── services/           # 业务逻辑
│   │   ├── tasks/              # Celery任务
│   │   ├── auth/               # 认证授权
│   │   ├── gpu/                # GPU管理
│   │   ├── files/              # 文件服务
│   │   ├── monitoring/         # 监控模块
│   │   ├── common/             # 通用工具
│   │   ├── config.py           # 配置文件
│   │   ├── database.py         # 数据库连接
│   │   ├── celery_app.py       # Celery应用
│   │   └── main.py             # FastAPI入口
│   ├── alembic/                # 数据库迁移
│   ├── tests/                  # 测试代码
│   ├── requirements.txt        # Python依赖
│   ├── Dockerfile              # Docker镜像
│   └── .env.example            # 环境变量示例
│
├── frontend/                   # 前端代码
│   ├── src/
│   │   ├── views/              # 页面组件
│   │   ├── components/         # 公共组件
│   │   ├── stores/             # Pinia Store
│   │   ├── router/             # 路由配置
│   │   ├── api/                # API封装
│   │   ├── utils/              # 工具函数
│   │   └── main.ts             # 入口文件
│   ├── public/                 # 静态资源
│   ├── package.json            # NPM依赖
│   ├── vite.config.ts          # Vite配置
│   ├── Dockerfile              # Docker镜像
│   └── .env.example            # 环境变量示例
│
├── monitoring/                 # 监控配置
│   ├── prometheus/
│   │   ├── prometheus.yml
│   │   └── alerts.yml
│   └── grafana/
│       └── dashboards/
│
├── docker-compose.yml          # Docker Compose配置
├── .gitignore
└── README.md                   # 本文件
```

---

## 🚀 快速开始

### 前置要求

- Docker 20.10+
- Docker Compose 2.0+
- Git

### 1. 克隆项目

```bash
git clone https://github.com/your-org/cpumodel_sciminer.git
cd cpumodel_sciminer
```

### 2. 配置环境变量

```bash
# 复制环境变量模板
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# 编辑backend/.env，配置数据库密码、JWT密钥等
vim backend/.env
```

**backend/.env 示例**：
```env
# 数据库配置
DB_HOST=postgres
DB_PORT=5432
DB_NAME=scitool_platform
DB_USER=scitool
DB_PASSWORD=your_secure_password

# Redis配置
REDIS_URL=redis://redis:6379/0

# MinIO配置
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=your_secure_secret

# JWT配置
JWT_SECRET_KEY=your_jwt_secret_key_here
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60

# Celery配置
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1

# 系统配置
PLATFORM_NAME=科学计算工具管理平台
PLATFORM_VERSION=1.0.0-MVP
```

### 3. 启动服务

```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f backend
```

### 4. 初始化数据库

数据库会在首次启动时自动初始化（通过`001_schema.sql`和`002_seed.sql`）。

如需手动执行：

```bash
# 进入PostgreSQL容器
docker-compose exec postgres psql -U scitool -d scitool_platform

# 执行SQL脚本
\i /docker-entrypoint-initdb.d/001_schema.sql
\i /docker-entrypoint-initdb.d/002_seed.sql
```

### 5. 访问系统

- **前端界面**：http://localhost:3000
- **后端API文档**：http://localhost:8000/docs
- **MinIO控制台**：http://localhost:9001 (admin / your_secret)
- **Prometheus**：http://localhost:9090
- **Grafana**：http://localhost:3001 (admin / admin)

### 6. 默认账户

系统预置了一个管理员账户：

- **邮箱**：`admin@example.com`
- **密码**：`Admin@123456`

**⚠️ 生产环境请立即修改默认密码！**

---

## 🛠️ 开发指南

### 本地开发环境搭建

#### 后端开发

```bash
cd backend

# 创建虚拟环境
python3.10 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 启动Celery Worker
celery -A app.celery_app worker --loglevel=info --queues=gpu_queue,cpu_queue,default

# 启动Celery Beat（定时任务）
celery -A app.celery_app beat --loglevel=info
```

#### 前端开发

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build
```

### 数据库迁移

使用Alembic进行数据库迁移：

```bash
cd backend

# 自动生成迁移脚本
alembic revision --autogenerate -m "描述变更内容"

# 执行迁移
alembic upgrade head

# 回滚一个版本
alembic downgrade -1

# 查看迁移历史
alembic history
```

### 代码规范

#### Python代码规范

- 遵循 [PEP 8](https://pep8.org/) 风格指南
- 使用 `black` 格式化代码
- 使用 `pylint` 进行静态检查
- 类型提示：强制使用类型注解

```bash
# 格式化代码
black backend/app

# 静态检查
pylint backend/app

# 类型检查
mypy backend/app
```

#### TypeScript代码规范

- 遵循 [Airbnb JavaScript Style Guide](https://github.com/airbnb/javascript)
- 使用 `ESLint` + `Prettier` 格式化
- 强制类型检查

```bash
# 格式化代码
npm run lint:fix

# 类型检查
npm run type-check
```

### 测试

#### 后端测试

```bash
cd backend

# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_auth.py

# 生成覆盖率报告
pytest --cov=app --cov-report=html
```

#### 前端测试

```bash
cd frontend

# 运行单元测试
npm run test:unit

# 运行端到端测试
npm run test:e2e
```

---

## 📚 API文档

### REST API

完整的API接口文档请参考：

- **Swagger UI**：http://localhost:8000/docs
- **ReDoc**：http://localhost:8000/redoc
- **接口规格说明书**：[docs/design/03-接口规格说明书.md](docs/design/03-接口规格说明书.md)

### WebSocket API

#### 任务进度推送

**端点**：`ws://localhost:8000/api/v1/ws/tasks/{task_id}?token=<jwt_token>`

**消息格式**：
```json
{
  "type": "progress",
  "data": {
    "task_id": "uuid",
    "status": "RUNNING",
    "progress": 0.65,
    "message": "Processing step 65/100",
    "timestamp": "2025-12-14T10:03:00Z"
  }
}
```

**消息类型**：
- `progress`：进度更新
- `log`：日志消息
- `completed`：任务完成
- `failed`：任务失败

---

## 🔧 配置说明

### 系统配置

系统配置存储在`system_config`表中，可通过API动态修改。

**主要配置项**：

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| guest_daily_task_limit | 5 | 游客每日任务配额 |
| user_daily_task_limit | 50 | 普通用户每日任务配额 |
| vip_daily_task_limit | 999999 | VIP用户每日任务配额 |
| max_file_size_guest_mb | 10 | 游客最大文件大小(MB) |
| max_file_size_user_mb | 100 | 普通用户最大文件大小(MB) |
| max_file_size_vip_mb | 1024 | VIP用户最大文件大小(MB) |
| file_retention_days_guest | 7 | 游客文件保留天数 |
| file_retention_days_user | 30 | 普通用户文件保留天数 |
| file_retention_days_vip | 90 | VIP用户文件保留天数 |
| task_timeout_sec | 600 | 任务默认超时时间(秒) |
| task_max_retries | 3 | 任务最大重试次数 |

### GPU配置

GPU节点需要手动注册到系统：

```bash
# 通过API注册GPU节点
curl -X POST "http://localhost:8000/api/v1/gpu/nodes" \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "hostname": "gpu-node-01",
    "gpu_name": "NVIDIA RTX 4090",
    "gpu_count": 2,
    "total_memory_mb": 24576,
    "metadata": {
      "cuda_version": "12.0",
      "driver_version": "535.104.05"
    }
  }'
```

---

## 📦 部署指南

### 生产环境部署

#### 1. 准备服务器

- **最低配置**：
  - CPU: 4核心
  - 内存: 16GB
  - 存储: 100GB SSD
  - 网络: 100Mbps

- **推荐配置**：
  - CPU: 8核心
  - 内存: 32GB
  - 存储: 500GB SSD
  - 网络: 1Gbps

#### 2. 安装依赖

```bash
# 安装Docker
curl -fsSL https://get.docker.com | sh

# 安装Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 验证安装
docker --version
docker-compose --version
```

#### 3. 克隆项目

```bash
git clone https://github.com/your-org/cpumodel_sciminer.git
cd cpumodel_sciminer
```

#### 4. 配置环境变量

```bash
# 复制环境变量模板
cp backend/.env.example backend/.env

# 生成安全的密钥
openssl rand -hex 32  # 用于JWT_SECRET_KEY
openssl rand -hex 16  # 用于DB_PASSWORD
openssl rand -hex 16  # 用于MINIO_SECRET_KEY

# 编辑.env文件，填入生成的密钥
vim backend/.env
```

#### 5. 修改生产配置

编辑`docker-compose.yml`：

```yaml
# 移除--reload参数
command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# 配置Nginx反向代理（推荐）
# 配置HTTPS证书
# 配置日志持久化
```

#### 6. 启动服务

```bash
# 拉取镜像
docker-compose pull

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

#### 7. 配置反向代理（Nginx）

```nginx
# /etc/nginx/sites-available/scitool

upstream backend {
    server localhost:8000;
}

upstream frontend {
    server localhost:3000;
}

server {
    listen 80;
    server_name your-domain.com;

    # 重定向到HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # 前端
    location / {
        proxy_pass http://frontend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # 后端API
    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket
    location /api/v1/ws/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

#### 8. 配置自动备份

```bash
# 创建备份脚本
cat > /scripts/backup_postgres.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/backups/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="scitool_platform"
FILENAME="${DB_NAME}_${DATE}.sql.gz"

mkdir -p "${BACKUP_DIR}"

docker-compose exec -T postgres pg_dump -U scitool ${DB_NAME} | gzip > "${BACKUP_DIR}/${FILENAME}"

# 删除7天前的备份
find "${BACKUP_DIR}" -name "*.sql.gz" -mtime +7 -delete

echo "Backup completed: ${FILENAME}"
EOF

chmod +x /scripts/backup_postgres.sh

# 添加Cron定时任务
crontab -e
# 添加以下行（每天凌晨4点备份）
0 4 * * * /scripts/backup_postgres.sh >> /var/log/backup_postgres.log 2>&1
```

#### 9. 配置监控告警

详见 [monitoring/README.md](monitoring/README.md)

---

## 🔍 故障排查

### 常见问题

#### 1. 数据库连接失败

**症状**：后端启动报错 `OperationalError: could not connect to server`

**排查步骤**：
```bash
# 检查PostgreSQL是否启动
docker-compose ps postgres

# 查看PostgreSQL日志
docker-compose logs postgres

# 检查环境变量配置
docker-compose exec backend env | grep DB_

# 手动测试连接
docker-compose exec backend python -c "from app.database import engine; print(engine)"
```

#### 2. Celery Worker无法连接Redis

**症状**：任务无法执行，日志显示 `Cannot connect to redis://`

**排查步骤**：
```bash
# 检查Redis是否启动
docker-compose ps redis

# 测试Redis连接
docker-compose exec backend python -c "import redis; r = redis.from_url('redis://redis:6379/0'); print(r.ping())"

# 检查Celery配置
docker-compose exec celery_worker celery -A app.celery_app inspect active
```

#### 3. MinIO文件上传失败

**症状**：文件上传返回 `S3Error`

**排查步骤**：
```bash
# 检查MinIO是否启动
docker-compose ps minio

# 检查MinIO日志
docker-compose logs minio

# 测试MinIO连接
docker-compose exec backend python -c "from app.files.minio_client import minio_client; print(minio_client.list_buckets())"
```

#### 4. GPU任务无法执行

**症状**：GPU任务一直处于PENDING状态

**排查步骤**：
```bash
# 检查GPU节点是否注册
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/gpu/nodes

# 检查GPU节点状态
nvidia-smi

# 检查Celery GPU队列
docker-compose exec celery_worker celery -A app.celery_app inspect reserved
```

### 日志查看

```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f backend
docker-compose logs -f celery_worker

# 查看最近100行日志
docker-compose logs --tail=100 backend

# 查看特定时间范围日志
docker-compose logs --since 2025-12-14T10:00:00 backend
```

---

## 🤝 贡献指南

欢迎贡献代码、报告Bug、提出功能建议！

### 贡献流程

1. **Fork本仓库**
2. **创建特性分支** (`git checkout -b feature/AmazingFeature`)
3. **提交改动** (`git commit -m 'Add some AmazingFeature'`)
4. **推送到分支** (`git push origin feature/AmazingFeature`)
5. **提交Pull Request**

### 开发规范

- 遵循现有代码风格
- 添加必要的测试用例
- 更新相关文档
- 提交前运行测试和代码检查

### Issue规范

**Bug Report模板**：
```markdown
### 问题描述
简要描述遇到的问题

### 复现步骤
1. 步骤1
2. 步骤2
3. ...

### 预期行为
描述期望的正确行为

### 实际行为
描述实际发生的错误行为

### 环境信息
- OS: [例如 Ubuntu 22.04]
- Python版本: [例如 3.10.12]
- 相关版本: [例如 FastAPI 0.109.0]

### 附加信息
- 错误日志
- 截图
```

**Feature Request模板**：
```markdown
### 功能描述
简要描述建议的新功能

### 使用场景
描述该功能解决的问题或满足的需求

### 实现建议
（可选）提供实现思路或参考方案

### 替代方案
（可选）描述替代解决方案
```

---

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源许可证。

---

## 📞 联系方式

- **项目主页**：https://github.com/your-org/cpumodel_sciminer
- **问题反馈**：https://github.com/your-org/cpumodel_sciminer/issues
- **邮箱**：support@example.com

---

## 🙏 致谢

感谢以下开源项目：

- [FastAPI](https://fastapi.tiangolo.com/) - 现代化的Python Web框架
- [Vue.js](https://vuejs.org/) - 渐进式JavaScript框架
- [PostgreSQL](https://www.postgresql.org/) - 强大的开源数据库
- [Celery](https://docs.celeryq.dev/) - 分布式任务队列
- [MinIO](https://min.io/) - 高性能对象存储
- [Element Plus](https://element-plus.org/) - Vue 3 UI组件库
- [ECharts](https://echarts.apache.org/) - 强大的数据可视化库

---

## 📊 项目状态

![GitHub commit activity](https://img.shields.io/github/commit-activity/m/your-org/cpumodel_sciminer)
![GitHub last commit](https://img.shields.io/github/last-commit/your-org/cpumodel_sciminer)
![GitHub issues](https://img.shields.io/github/issues/your-org/cpumodel_sciminer)
![GitHub pull requests](https://img.shields.io/github/issues-pr/your-org/cpumodel_sciminer)

---

**版本**：1.0.0-MVP
**最后更新**：2025-12-14
