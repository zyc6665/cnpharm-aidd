# Celery + Redis 快速参考

## 🚀 一键启动

```bash
./start-celery.sh
```

**首次启动**（需要构建镜像）：
```bash
./start-celery.sh --build
```

---

## 📊 服务访问

| 服务 | 地址 | 登录信息 |
|------|------|---------|
| **Flower监控** | http://localhost:5555 | admin / scitool123 |
| **Redis** | localhost:6379 | 密码: scitool123 |

---

## 🔧 常用命令

### 服务管理

```bash
# 启动
docker-compose -f docker-compose.celery.yml up -d

# 停止
docker-compose -f docker-compose.celery.yml down

# 重启
docker-compose -f docker-compose.celery.yml restart

# 查看状态
docker-compose -f docker-compose.celery.yml ps

# 查看日志
docker-compose -f docker-compose.celery.yml logs -f celery-worker
```

### Celery任务管理

```bash
# 进入Worker容器
docker exec -it scitool-celery-worker bash

# 查看活跃任务
docker-compose -f docker-compose.celery.yml exec celery-worker \
  celery -A app.worker.celery_app inspect active

# 查看注册任务
docker-compose -f docker-compose.celery.yml exec celery-worker \
  celery -A app.worker.celery_app inspect registered

# 查看Worker统计
docker-compose -f docker-compose.celery.yml exec celery-worker \
  celery -A app.worker.celery_app inspect stats
```

### Redis管理

```bash
# 进入Redis CLI
docker exec -it scitool-redis redis-cli -a scitool123

# 测试连接
docker-compose -f docker-compose.celery.yml exec redis \
  redis-cli -a scitool123 ping

# 查看信息
docker-compose -f docker-compose.celery.yml exec redis \
  redis-cli -a scitool123 info

# 查看内存
docker-compose -f docker-compose.celery.yml exec redis \
  redis-cli -a scitool123 info memory
```

---

## 🐛 故障排查

### 1. 检查服务健康状态

```bash
docker-compose -f docker-compose.celery.yml ps
```

### 2. 查看错误日志

```bash
# Worker日志
docker-compose -f docker-compose.celery.yml logs --tail=50 celery-worker

# Redis日志
docker-compose -f docker-compose.celery.yml logs --tail=50 redis
```

### 3. 重启问题服务

```bash
# 重启Worker
docker-compose -f docker-compose.celery.yml restart celery-worker

# 重启Redis
docker-compose -f docker-compose.celery.yml restart redis
```

### 4. 完全重建

```bash
# 停止并删除容器
docker-compose -f docker-compose.celery.yml down -v

# 重新构建并启动
docker-compose -f docker-compose.celery.yml up -d --build
```

---

## ⚙️ 配置文件位置

| 文件 | 路径 | 说明 |
|------|------|------|
| Docker Compose | `docker-compose.celery.yml` | 服务编排配置 |
| 环境变量 | `backend/.env` | Redis/Celery配置 |
| 后端配置 | `backend/app/config.py` | 读取环境变量 |
| Celery应用 | `backend/app/celery_app/__init__.py` | Celery初始化 |

---

## 📈 监控指标

### Flower界面查看

1. 打开 http://localhost:5555
2. 查看 **Dashboard** - Worker状态、任务统计
3. 查看 **Tasks** - 任务列表和详情
4. 查看 **Workers** - Worker详细信息

### Redis监控

```bash
# 内存使用
docker exec scitool-redis redis-cli -a scitool123 info memory | grep used_memory_human

# 队列长度
docker exec scitool-redis redis-cli -a scitool123 llen celery

# 连接数
docker exec scitool-redis redis-cli -a scitool123 info clients | grep connected_clients
```

---

## 🔒 安全提示

⚠️ **生产环境必须修改**：

1. **Redis密码**：修改 `docker-compose.celery.yml` 和 `backend/.env` 中的 `scitool123`
2. **Flower密码**：修改 `docker-compose.celery.yml` 中的 `admin:scitool123`
3. **端口绑定**：生产环境绑定到内网IP，不暴露到公网

---

## 📚 完整文档

- **部署指南**: [CELERY_DEPLOYMENT.md](./CELERY_DEPLOYMENT.md)
- **实施方案**: [docs/design/07-任务执行引擎完整实施方案.md](./docs/design/07-任务执行引擎完整实施方案.md)

---

**快速帮助**: 遇到问题查看 `CELERY_DEPLOYMENT.md` 的故障排查章节
