# 快速启动指南

## 🚀 一键启动（推荐）

```bash
# 启动开发环境
./scripts/start-dev.sh
```

启动脚本会自动：
- ✅ 检测 Docker 和 Docker Compose 版本
- ✅ 创建必要的网络
- ✅ 构建开发镜像
- ✅ 启动所有服务
- ✅ 显示访问地址

## 📦 手动启动

### 使用 Docker Compose v2（推荐）

Docker Compose v2 随 Docker Desktop 自动安装，命令格式为 `docker compose`（注意是空格而不是连字符）。

```bash
# 查看版本
docker compose version

# 启动所有服务
docker compose up -d

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f backend

# 停止服务
docker compose down
```

### 使用 Docker Compose v1（传统）

如果您使用独立安装的 docker-compose，命令格式为 `docker-compose`（连字符）。

```bash
# 查看版本
docker-compose version

# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f backend

# 停止服务
docker-compose down
```

## 🔧 配置文件说明

### deploy/compose/docker-compose.dev.yml 版本兼容

已移除 `version` 字段以支持最新的 Compose 规范，同时兼容 v1 和 v2。

```yaml
# ✅ 现在的格式（无 version 字段）
services:
  backend:
    image: scitool-backend:dev
    ...

# ❌ 旧格式（可能不兼容）
# version: "3.8"
# services:
#   ...
```

## 📋 服务访问

启动成功后可以访问：

| 服务 | 地址 | 凭据 |
|------|------|------|
| 后端 API | http://localhost:8000 | - |
| API 文档 | http://localhost:8000/docs | - |
| Flower 监控 | http://localhost:9555 | admin / scitool123 |
| Redis | localhost:9500 | password: scitool123 |

## 🐛 常见问题

### 1. 提示 "unsupported version"

**原因**: 旧版 docker-compose 不支持 `version: "3.8"`

**解决方案**:
```bash
# 方案1: 使用最新的 deploy/compose/docker-compose.dev.yml（已移除 version 字段）
git pull  # 更新代码

# 方案2: 升级 Docker Compose
# Docker Desktop 用户会自动获得 v2
# 独立安装：pip install --upgrade docker-compose
```

### 2. docker-compose 命令不存在

**Docker Desktop 用户**:
```bash
# 使用 v2 语法（空格）
docker compose up -d
```

**独立安装用户**:
```bash
# 安装 docker-compose
pip install docker-compose

# 或使用系统包管理器
sudo apt-get install docker-compose  # Debian/Ubuntu
sudo yum install docker-compose       # CentOS/RHEL
```

### 3. 权限被拒绝

```bash
# 添加当前用户到 docker 组
sudo usermod -aG docker $USER

# 重新登录或执行
newgrp docker

# 或使用 sudo
sudo docker compose up -d
```

### 4. 端口已被占用

```bash
# 检查端口占用
lsof -i :8000  # 后端
lsof -i :9500  # Redis
lsof -i :9555  # Flower

# 修改端口（编辑 deploy/compose/docker-compose.dev.yml）
ports:
  - "8001:8000"  # 将宿主机端口改为 8001
```

### 5. 容器无法启动

```bash
# 查看详细错误
docker compose logs backend

# 重新构建镜像
docker compose build --no-cache backend

# 强制重建容器
docker compose up -d --force-recreate backend
```

## 💡 开发技巧

### 热重载测试

```bash
# 1. 启动环境
docker compose up -d

# 2. 查看后端日志
docker compose logs -f backend

# 3. 修改代码（在另一个终端）
echo "# test change" >> backend/app/main.py

# 4. 观察日志中的重载信息
# 应该看到: "WatchFiles detected changes... Reloading..."
```

### 进入容器调试

```bash
# 进入后端容器
docker compose exec backend bash

# 查看文件
ls -la /app/app/

# 测试 Python 代码
python
>>> from app.models.users import User
>>> # 调试代码
```

### 数据库操作

```bash
# 进入容器
docker compose exec backend bash

# 使用 SQLite
sqlite3 /app/storage/scitool.db

# 查看表
.tables

# 执行 SQL
SELECT * FROM users;
```

## 📚 更多帮助

- 详细开发文档: [DEVELOPMENT.md](./DEVELOPMENT.md)
- Docker Compose 文档: https://docs.docker.com/compose/
- 项目架构说明: [docs/design/](./docs/design/)

## ✅ 验证安装

运行以下命令验证环境：

```bash
# 1. 检查服务状态
docker compose ps
# 期望: 所有服务 State 为 Up

# 2. 测试 API
curl http://localhost:8000/api/v1/system/health
# 期望: {"status":"healthy",...}

# 3. 测试 Redis
docker compose exec redis redis-cli -a scitool123 ping
# 期望: PONG

# 4. 访问 API 文档
# 浏览器打开: http://localhost:8000/docs
# 期望: 看到 Swagger UI 界面
```

全部通过即表示环境配置成功！ 🎉
