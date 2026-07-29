# Celery + Redis 部署指南

## 📋 概述

本文档说明如何部署和使用**Celery异步任务队列**和**Redis消息代理**，用于SciTool平台的任务执行引擎。

---

## 🚀 快速开始

### 1. 前置条件检查

```bash
# 检查Docker版本
docker --version
# 应输出: Docker version 20.x 或更高

# 检查Docker Compose版本
docker-compose --version
# 应输出: Docker Compose version 2.x 或更高

# 检查cpumodel网络是否存在
docker network ls | grep cpumodel
```

### 2. 创建网络（如不存在）

```bash
# 创建cpumodel网络
docker network create cpumodel

# 验证网络创建成功
docker network inspect cpumodel
```

### 3. 启动Celery + Redis服务

```bash
# 进入项目根目录
cd /data/zhouyc/cpumodel_sciminer

# 启动所有服务
docker-compose -f docker-compose.celery.yml up -d

# 查看服务状态
docker-compose -f docker-compose.celery.yml ps
```

**预期输出**：
```
NAME                        STATUS              PORTS
scitool-redis               Up (healthy)        0.0.0.0:9500->6379/tcp
scitool-celery-worker       Up (healthy)
scitool-celery-worker-gpu   Up
scitool-flower              Up (healthy)        0.0.0.0:9555->9555/tcp
```

### 4. 验证服务运行

```bash
# 1. 测试Redis连接
docker-compose -f docker-compose.celery.yml exec redis \
  redis-cli -a scitool123 ping
# 应输出: PONG

# 2. 查看Celery Worker状态
docker-compose -f docker-compose.celery.yml exec celery-worker \
  celery -A app.worker.celery_app inspect stats

# 3. 访问Flower监控面板
# 浏览器打开: http://localhost:9555
# 登录账号: admin
# 登录密码: scitool123
```

---

## 📊 监控和管理

### Flower Web监控面板

**访问地址**: http://localhost:9555

**功能**：
- ✅ 实时查看Worker状态
- ✅ 监控任务执行情况（成功/失败/重试）
- ✅ 查看任务队列长度
- ✅ 查看Worker资源占用（CPU、内存）
- ✅ 手动终止任务
- ✅ 查看任务执行历史

**默认登录**：
- 用户名: `admin`
- 密码: `scitool123`

### Celery命令行管理

```bash
# 查看活跃任务
docker-compose -f docker-compose.celery.yml exec celery-worker \
  celery -A app.worker.celery_app inspect active

# 查看注册的任务列表
docker-compose -f docker-compose.celery.yml exec celery-worker \
  celery -A app.worker.celery_app inspect registered

# 查看Worker详细统计
docker-compose -f docker-compose.celery.yml exec celery-worker \
  celery -A app.worker.celery_app inspect stats

# 清空任务队列（慎用！）
docker-compose -f docker-compose.celery.yml exec celery-worker \
  celery -A app.worker.celery_app purge

# 取消特定任务
docker-compose -f docker-compose.celery.yml exec celery-worker \
  celery -A app.worker.celery_app control revoke <task_id>
```

### Redis监控命令

```bash
# 查看Redis信息
docker-compose -f docker-compose.celery.yml exec redis \
  redis-cli -a scitool123 info

# 查看内存使用
docker-compose -f docker-compose.celery.yml exec redis \
  redis-cli -a scitool123 info memory

# 查看队列长度
docker-compose -f docker-compose.celery.yml exec redis \
  redis-cli -a scitool123 llen celery

# 查看所有key
docker-compose -f docker-compose.celery.yml exec redis \
  redis-cli -a scitool123 keys '*'
```

---

## 🔧 日常操作

### 启动/停止服务

```bash
# 启动服务
docker-compose -f docker-compose.celery.yml up -d

# 停止服务
docker-compose -f docker-compose.celery.yml down

# 重启服务
docker-compose -f docker-compose.celery.yml restart

# 重启单个服务
docker-compose -f docker-compose.celery.yml restart celery-worker
```

### 查看日志

```bash
# 查看所有服务日志
docker-compose -f docker-compose.celery.yml logs -f

# 查看Worker日志
docker-compose -f docker-compose.celery.yml logs -f celery-worker

# 查看Redis日志
docker-compose -f docker-compose.celery.yml logs -f redis

# 查看最近100行日志
docker-compose -f docker-compose.celery.yml logs --tail=100 celery-worker
```

### 更新服务

```bash
# 重新构建镜像
docker-compose -f docker-compose.celery.yml build --no-cache

# 重新启动服务
docker-compose -f docker-compose.celery.yml up -d --force-recreate
```

---

## 🐛 故障排查

### 问题1: Worker无法连接Redis

**症状**：
```
celery.exceptions.OperationalError: Error 111 connecting to redis:6379. Connection refused.
```

**解决方案**：
```bash
# 1. 检查Redis是否运行
docker ps | grep redis

# 2. 检查网络连接
docker network inspect cpumodel

# 3. 检查Redis密码配置
# 确保 .env 和 docker-compose.celery.yml 中的密码一致

# 4. 重启Redis
docker-compose -f docker-compose.celery.yml restart redis
```

### 问题2: 任务一直处于PENDING状态

**症状**：
- 前端显示任务状态为PENDING
- Flower中看不到任务执行

**解决方案**：
```bash
# 1. 检查Worker是否运行
docker ps | grep celery-worker

# 2. 查看Worker日志
docker-compose -f docker-compose.celery.yml logs celery-worker

# 3. 检查任务队列
docker-compose -f docker-compose.celery.yml exec redis \
  redis-cli -a scitool123 llen celery

# 4. 检查任务注册
docker-compose -f docker-compose.celery.yml exec celery-worker \
  celery -A app.worker.celery_app inspect registered
```

### 问题3: GPU Worker无法启动

**症状**：
```
could not select device driver "" with capabilities: [[gpu]]
```

**解决方案**：
```bash
# 1. 检查NVIDIA驱动
nvidia-smi

# 2. 检查NVIDIA Container Toolkit
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi

# 3. 如无GPU，注释掉docker-compose.celery.yml中的celery-worker-gpu服务
```

### 问题4: Flower无法访问

**症状**：
- 浏览器无法打开 http://localhost:9555

**解决方案**：
```bash
# 1. 检查Flower容器状态
docker ps | grep flower

# 2. 检查端口占用
netstat -nltp | grep 9555

# 3. 检查Flower日志
docker-compose -f docker-compose.celery.yml logs flower

# 4. 重启Flower
docker-compose -f docker-compose.celery.yml restart flower
```

### 问题5: 数据库连接错误

**症状**：
```
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) unable to open database file
```

**解决方案**：
```bash
# 确保数据库文件挂载正确
# 检查 docker-compose.celery.yml 中的 volumes 配置
volumes:
  - ./backend/storage:/app/storage

# 检查文件权限
ls -la backend/storage/scitool.db
chmod 666 backend/storage/scitool.db
```

---

## ⚙️ 配置优化

### Worker并发数调整

**默认队列Worker** (docker-compose.celery.yml):
```yaml
command: >
  celery -A app.worker.celery_app worker
  --concurrency=4          # 调整并发数（建议: CPU核心数）
```

**GPU队列Worker**:
```yaml
command: >
  celery -A app.worker.celery_app worker
  --concurrency=1          # GPU任务通常设为1
```

### Redis内存限制

**修改 docker-compose.celery.yml**:
```yaml
redis:
  command: >
    redis-server
    --maxmemory 4gb        # 增大内存限制
    --maxmemory-policy allkeys-lru
```

### 任务超时配置

**修改 backend/.env**:
```env
# 软超时（秒）- 发出警告但继续执行
CELERY_TASK_SOFT_TIME_LIMIT=3600

# 硬超时（秒）- 强制终止任务
CELERY_TASK_TIME_LIMIT=7200
```

---

## 🔒 安全配置

### 生产环境配置

**1. 修改默认密码**：

编辑 `docker-compose.celery.yml`:
```yaml
redis:
  command: >
    redis-server
    --requirepass <your-strong-password>

celery-worker:
  environment:
    REDIS_PASSWORD: <your-strong-password>
    CELERY_BROKER_URL: redis://:<your-strong-password>@redis:6379/1
```

**2. Flower认证**：
```yaml
flower:
  command: >
    celery flower
    --basic_auth=<username>:<strong-password>
```

**3. 限制网络访问**：
```yaml
redis:
  ports:
    # 生产环境不暴露端口，仅内部访问
    # - "6379:6379"  # 注释掉

flower:
  ports:
    # 使用内网IP限制访问
    - "127.0.0.1:9555:9555"
```

---

## 📈 性能优化建议

### 1. Worker进程池类型

**默认（prefork）**：
- 适合CPU密集型任务
- 每个worker是独立进程

**gevent（协程）**：
- 适合I/O密集型任务（如API调用）
- 更高并发

```yaml
command: >
  celery -A app.worker.celery_app worker
  --pool=gevent           # 使用协程池
  --concurrency=100       # 协程可以设置更高并发
```

### 2. 结果过期时间

**backend/app/worker/celery_app.py**:
```python
celery_app.conf.update(
    result_expires=3600,  # 1小时后过期（减少Redis内存占用）
)
```

### 3. 队列优先级

```python
# 发送高优先级任务
celery_app.send_task(
    'execute_tool_task',
    args=[...],
    priority=9  # 0-9，数字越大优先级越高
)
```

---

## 📝 开发调试

### 本地开发模式

**不使用Docker运行Worker**：

```bash
# 1. 启动Redis（使用Docker）
docker-compose -f docker-compose.celery.yml up -d redis

# 2. 安装依赖
cd backend
pip install -r requirements.txt

# 3. 本地启动Worker
celery -A app.worker.celery_app worker --loglevel=debug

# 4. 本地启动Flower
celery -A app.worker.celery_app flower --port=9555
```

### 测试任务执行

**Python测试脚本** (test_celery.py):
```python
from app.worker.celery_app import celery_app

# 发送测试任务
result = celery_app.send_task(
    'execute_tool_task',
    args=[
        'test-task-id',
        {'type': 'remote_api', 'endpoint': 'https://httpbin.org/post'},
        {'test': 'data'},
        []
    ]
)

print(f"Task ID: {result.id}")
print(f"Status: {result.status}")
print(f"Result: {result.get(timeout=60)}")
```

---

## 🗂️ 数据持久化

### Redis数据备份

```bash
# 手动触发RDB快照
docker-compose -f docker-compose.celery.yml exec redis \
  redis-cli -a scitool123 bgsave

# 导出Redis数据
docker-compose -f docker-compose.celery.yml exec redis \
  redis-cli -a scitool123 --rdb /data/dump.rdb

# 复制备份文件
docker cp scitool-redis:/data/dump.rdb ./backup/redis-$(date +%Y%m%d).rdb
```

### 数据恢复

```bash
# 停止Redis
docker-compose -f docker-compose.celery.yml stop redis

# 恢复备份文件
docker cp ./backup/redis-20251219.rdb scitool-redis:/data/dump.rdb

# 启动Redis
docker-compose -f docker-compose.celery.yml start redis
```

---

## 📚 相关文档

- [Celery官方文档](https://docs.celeryq.dev/)
- [Redis官方文档](https://redis.io/documentation)
- [Flower文档](https://flower.readthedocs.io/)
- [任务执行引擎完整实施方案](./docs/design/07-任务执行引擎完整实施方案.md)

---

## ✅ 验收检查清单

部署完成后，请逐项检查：

- [ ] Redis容器正常运行 (`docker ps | grep redis`)
- [ ] Celery Worker容器正常运行 (`docker ps | grep celery-worker`)
- [ ] Redis连接测试通过 (`redis-cli ping`)
- [ ] Flower监控面板可访问 (http://localhost:9555)
- [ ] Worker注册任务可见 (`celery inspect registered`)
- [ ] 测试任务执行成功
- [ ] 日志正常输出无错误

---

**部署完成时间**: _______________

**部署人员**: _______________

**备注**: _______________
