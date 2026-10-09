# SciTool 开发环境指南

## 🚀 快速开始

### 一键启动（推荐）

```bash
# 1. 启动开发环境（包含后端 + Redis + Celery + Flower）
./scripts/start-dev.sh

# 2. 等待服务启动完成后访问:
# - API 文档: http://localhost:8000/docs
# - Flower 监控: http://localhost:9555 (admin/scitool123)
```

### 手动启动

```bash
# 1. 创建 Docker 网络
docker network create cpumodel

# 2. 启动所有服务
docker-compose up -d

# 3. 查看服务状态
docker-compose ps

# 4. 查看后端日志
docker-compose logs -f backend
```

## 📂 项目结构

```
scitool/
├── backend/                    # 后端代码（挂载到容器）
│   ├── app/                   # ✨ 修改这里的代码会自动重载！
│   │   ├── main.py           # FastAPI 主应用
│   │   ├── api/              # API 路由
│   │   ├── models/           # 数据库模型
│   │   ├── tasks/            # 任务执行器
│   │   ├── worker/           # Celery 配置
│   │   └── ...
│   ├── storage/              # 数据库和上传文件（挂载）
│   ├── requirements.txt      # Python 依赖
│   └── Dockerfile            # 后端镜像构建
├── deploy/compose/docker-compose.dev.yml        # 开发环境配置
└── scripts/start-dev.sh      # 一键启动脚本
```

## 🔥 热重载功能

### 后端热重载
- **修改代码**: 编辑 `backend/app/` 下的任何 `.py` 文件
- **自动生效**: Uvicorn 自动检测变化并重启服务（1-2 秒）
- **无需操作**: 不需要手动重启容器！

```python
# 示例：修改 backend/app/api/v1/system.py
@router.get("/hello")
async def hello():
    return {"message": "Hello, World!"}  # 保存后立即生效
```

### Celery Worker 热重载
- **修改代码**: 编辑 `backend/app/worker/` 或 `backend/app/tasks/`
- **自动重启**: `watchfiles` 监控文件变化并重启 Worker
- **查看日志**: `docker-compose logs -f celery-worker`

### 不会热重载的修改
以下修改需要重新构建镜像：
- 修改 `requirements.txt` (新增/删除依赖)
- 修改 `Dockerfile`
- 修改系统配置

```bash
# 重新构建并启动
docker-compose build --no-cache backend
docker-compose up -d --force-recreate backend
```

## 🛠️ 开发工作流

### 1. 开发新功能

```bash
# 1. 启动开发环境
./scripts/start-dev.sh

# 2. 在 VSCode/PyCharm 中编辑代码
# 修改: backend/app/api/v1/xxx.py

# 3. 保存文件后，后端自动重载

# 4. 测试 API
curl http://localhost:8000/api/v1/xxx
# 或访问: http://localhost:8000/docs

# 5. 查看日志
docker-compose logs -f backend
```

### 2. 调试代码

```bash
# 方法1: 在代码中添加日志
import logging
logger = logging.getLogger(__name__)

def my_function():
    logger.info("调试信息")
    logger.error("错误信息")

# 方法2: 进入容器调试
docker-compose exec backend bash

# 进入 Python Shell
python
>>> from app.models.users import User
>>> # 测试代码

# 方法3: 查看实时日志
docker-compose logs -f backend
```

### 3. 测试任务执行

```bash
# 1. 确保 Celery Worker 运行中
docker-compose ps celery-worker

# 2. 创建测试任务（通过 API）
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "tool_id": "xxx",
    "params": {"test": "value"}
  }'

# 3. 查看任务执行日志
docker-compose logs -f celery-worker

# 4. 在 Flower 中监控任务
# 访问: http://localhost:9555
```

### 4. 数据库操作

```bash
# 进入容器
docker-compose exec backend bash

# 使用 SQLite CLI
sqlite3 /app/storage/scitool.db

# 或使用 Python
python
>>> from app.database.session import async_session_factory
>>> # 数据库操作
```

## 📝 常用命令

### Docker Compose 命令

```bash
# 启动所有服务
docker-compose up -d

# 启动指定服务
docker-compose up -d backend redis

# 查看服务状态
docker-compose ps

# 查看日志（实时）
docker-compose logs -f backend
docker-compose logs -f celery-worker

# 查看日志（最近100行）
docker-compose logs --tail=100 backend

# 重启服务
docker-compose restart backend
docker-compose restart celery-worker

# 停止服务
docker-compose stop

# 停止并删除容器
docker-compose down

# 停止并删除容器+数据卷
docker-compose down -v

# 进入容器
docker-compose exec backend bash
docker-compose exec redis redis-cli -a scitool123

# 查看容器资源占用
docker stats
```

### 开发专用命令

```bash
# 重新构建镜像（修改依赖后）
docker-compose build --no-cache backend

# 强制重新创建容器
docker-compose up -d --force-recreate backend

# 查看网络
docker network inspect cpumodel

# 清理所有停止的容器
docker container prune

# 清理所有未使用的镜像
docker image prune -a
```

### Celery 命令

```bash
# 查看活跃任务
docker-compose exec celery-worker \
  celery -A app.worker.celery_app inspect active

# 查看注册的任务
docker-compose exec celery-worker \
  celery -A app.worker.celery_app inspect registered

# 查看 Worker 状态
docker-compose exec celery-worker \
  celery -A app.worker.celery_app inspect stats

# 清空任务队列
docker-compose exec celery-worker \
  celery -A app.worker.celery_app purge
```

### Redis 命令

```bash
# 进入 Redis CLI
docker-compose exec redis redis-cli -a scitool123

# 查看所有键
KEYS *

# 查看队列长度
LLEN celery

# 查看内存使用
INFO memory

# 清空所有数据（慎用！）
FLUSHALL
```

## 🔍 故障排查

### 后端无法启动

```bash
# 1. 查看日志
docker-compose logs backend

# 2. 检查端口占用
lsof -i :8000

# 3. 重新构建镜像
docker-compose build --no-cache backend
docker-compose up -d --force-recreate backend

# 4. 检查环境变量
docker-compose exec backend env | grep -E "REDIS|CELERY|DATABASE"
```

### 热重载不生效

```bash
# 1. 确认代码挂载
docker-compose exec backend ls -la /app/app/

# 2. 检查文件权限
ls -la backend/app/

# 3. 查看 uvicorn 日志（应该看到 "Reloading..." 信息）
docker-compose logs -f backend

# 4. 手动重启服务
docker-compose restart backend
```

### Celery Worker 无法连接

```bash
# 1. 检查 Redis 连接
docker-compose exec backend redis-cli -h redis -p 6379 -a scitool123 ping

# 2. 查看 Worker 日志
docker-compose logs celery-worker

# 3. 检查网络
docker network inspect cpumodel

# 4. 重启 Worker
docker-compose restart celery-worker
```

### 任务一直 PENDING

```bash
# 1. 确认 Worker 运行
docker-compose ps celery-worker

# 2. 查看队列
docker-compose exec redis redis-cli -a scitool123 llen celery

# 3. 检查 Worker 监听的队列
docker-compose logs celery-worker | grep "queues"

# 4. 查看 Flower 监控
# 访问: http://localhost:9555
```

## 🌐 API 开发示例

### 1. 添加新的 API 端点

```python
# backend/app/api/v1/example.py
from fastapi import APIRouter, Depends
from app.common.responses import success_response

router = APIRouter()

@router.get("/hello")
async def hello(name: str = "World"):
    """示例端点"""
    return success_response(
        data={"message": f"Hello, {name}!"}
    )
```

```python
# backend/app/api/v1/__init__.py
from .example import router as example_router

# 注册路由
api_router.include_router(
    example_router,
    prefix="/example",
    tags=["示例"]
)
```

保存后访问: http://localhost:8000/api/v1/example/hello?name=Developer

### 2. 添加新的 Celery 任务

```python
# backend/app/worker/tasks.py
from celery import shared_task

@shared_task(name="app.worker.tasks.example_task")
def example_task(param: str):
    """示例任务"""
    logger.info(f"执行任务，参数: {param}")
    return {"result": f"处理完成: {param}"}
```

保存后，Worker 会自动重载并注册新任务。

在 API 中调用：
```python
from app.worker.tasks import example_task

# 异步执行
celery_task = example_task.delay("test")
```

## 📊 性能监控

### Flower 监控面板
- 访问: http://localhost:9555
- 用户名: admin
- 密码: scitool123

功能:
- 查看活跃任务
- 监控 Worker 状态
- 查看任务执行历史
- 实时任务流量图表

### Docker 资源监控

```bash
# 查看容器资源占用
docker stats

# 查看特定容器
docker stats scitool-backend scitool-celery-worker
```

## 🔒 环境变量配置

开发环境环境变量在 `deploy/compose/docker-compose.dev.yml` 中配置，也可以通过 `.env` 文件覆盖：

```bash
# backend/.env
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=scitool123

CELERY_BROKER_URL=redis://:scitool123@redis:6379/1
CELERY_RESULT_BACKEND=redis://:scitool123@redis:6379/2

DATABASE_URL=sqlite+aiosqlite:///./storage/scitool.db
```

## 🎯 下一步

1. ✅ 启动开发环境
2. ✅ 修改代码并测试热重载
3. ✅ 通过 API 文档测试接口
4. ✅ 创建 Celery 任务并监控
5. 📝 编写测试用例
6. 🚀 准备生产部署

## 📚 相关文档

- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [Celery 官方文档](https://docs.celeryq.dev/)
- [Docker Compose 文档](https://docs.docker.com/compose/)
- [Redis 命令参考](https://redis.io/commands/)

## ❓ 获取帮助

遇到问题？
1. 查看日志: `docker-compose logs -f backend`
2. 检查健康状态: `docker-compose ps`
3. 查阅本文档的故障排查部分
4. 提交 Issue 到项目仓库

---

**Happy Coding! 🎉**
