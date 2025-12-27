# 启动脚本使用指南

## 🚀 start-dev.sh 优化说明

### 主要改进

✅ **智能镜像检测**
- 自动检测镜像是否已存在
- 第二次启动时不会强制重新构建
- 询问用户是否需要重建

✅ **快速启动模式**
- 跳过所有交互式确认
- 适合日常开发快速启动

✅ **强制重建模式**
- 修改依赖后需要重建镜像
- 使用 `--no-cache` 清理缓存

## 📝 使用方法

### 1. 交互模式（默认）

```bash
./start-dev.sh
```

**流程**:
1. 检查 Docker 环境
2. 检查/创建网络
3. 询问是否清理旧容器
4. **检测镜像是否存在**
   - 存在 → 询问是否重建
   - 不存在 → 自动构建
5. 启动所有服务
6. 询问是否查看日志

**适用场景**:
- 首次启动
- 需要选择性操作

### 2. 快速启动模式

```bash
./start-dev.sh --quick
# 或
./start-dev.sh -q
```

**特点**:
- ✅ 跳过容器清理确认
- ✅ 镜像存在则直接使用
- ✅ 跳过日志查看确认
- ⚡ 启动速度最快

**适用场景**:
- 日常开发启动
- CI/CD 自动化
- 镜像已构建好

**示例输出**:
```
✅ 检测到已存在的开发镜像
ℹ️  快速模式：使用现有镜像
✅ 所有服务已启动
ℹ️  快速模式：跳过日志查看
```

### 3. 强制重建模式

```bash
./start-dev.sh --rebuild
# 或
./start-dev.sh -r
```

**特点**:
- 🔨 使用 `--no-cache` 强制重建
- 🧹 清除所有构建缓存
- ⏱️ 构建时间较长（~2分钟）

**适用场景**:
- 修改了 `requirements.txt`
- 修改了 `Dockerfile`
- 镜像出现问题

**示例输出**:
```
ℹ️  强制重建模式：开始重新构建后端镜像...
✅ 镜像重新构建完成
```

### 4. 组合使用

```bash
# 重建后快速启动（不查看日志）
./start-dev.sh --rebuild --quick
```

### 5. 帮助信息

```bash
./start-dev.sh --help
# 或
./start-dev.sh -h
```

## 🎯 使用场景对比

| 场景 | 命令 | 是否构建 | 交互确认 | 启动速度 |
|------|------|----------|----------|----------|
| **首次启动** | `./start-dev.sh` | ✅ 自动 | ✅ 有 | 慢（~2分钟） |
| **日常开发** | `./start-dev.sh --quick` | ❌ 跳过 | ❌ 无 | 快（~10秒） |
| **修改依赖** | `./start-dev.sh --rebuild` | ✅ 强制 | ✅ 有 | 慢（~2分钟） |
| **CI/CD** | `./start-dev.sh --quick` | ❌ 跳过 | ❌ 无 | 快（~10秒） |
| **排查问题** | `./start-dev.sh --rebuild` | ✅ 清理缓存 | ✅ 有 | 慢（~2分钟） |

## 📊 启动流程对比

### 交互模式
```
启动脚本
    ↓
检查 Docker        (5秒)
    ↓
创建网络           (2秒)
    ↓
清理旧容器？       [询问用户]
    ↓
检查镜像
    ├─ 存在 → 重建？  [询问用户]
    └─ 不存在 → 构建   (2分钟)
    ↓
启动服务           (10秒)
    ↓
检查状态           (8秒)
    ↓
查看日志？         [询问用户]
```

### 快速模式
```
启动脚本
    ↓
检查 Docker        (5秒)
    ↓
创建网络           (2秒)
    ↓
跳过清理           [自动跳过]
    ↓
检查镜像
    └─ 存在 → 使用    [自动跳过]
    ↓
启动服务           (10秒)
    ↓
检查状态           (8秒)
    ↓
跳过日志           [自动跳过]

总耗时: ~25秒
```

## 🔍 镜像检测逻辑

```bash
# 检测命令
docker images | grep -q "scitool-backend.*dev"

# 如果镜像存在
✅ 检测到已存在的开发镜像

# 如果镜像不存在
ℹ️  未检测到开发镜像，开始构建...
```

## 💡 常见问题

### Q1: 第二次启动还要构建？

**原因**: 镜像名称不匹配或被删除

**解决**:
```bash
# 检查镜像
docker images | grep scitool-backend

# 应该看到:
# scitool-backend  dev  xxx  ~650MB

# 如果没有，重新构建
./start-dev.sh --rebuild
```

### Q2: 想跳过所有确认直接启动？

**解决**:
```bash
./start-dev.sh --quick
```

### Q3: 修改了 requirements.txt 怎么办？

**解决**:
```bash
# 强制重建镜像
./start-dev.sh --rebuild
```

### Q4: 镜像有问题，想清理缓存重建？

**解决**:
```bash
# 1. 删除旧镜像
docker rmi scitool-backend:dev

# 2. 强制重建（清理缓存）
./start-dev.sh --rebuild
```

### Q5: 怎么在 CI/CD 中使用？

**解决**:
```bash
# .gitlab-ci.yml 或 .github/workflows/xxx.yml
script:
  - ./start-dev.sh --quick
  - # 运行测试
```

## 🎓 最佳实践

### 日常开发工作流

```bash
# 早上开始工作
./start-dev.sh --quick

# 修改代码（自动热重载）
vim backend/app/api/v1/tasks.py

# 查看日志
docker compose logs -f backend

# 下班停止服务
docker compose down
```

### 修改依赖工作流

```bash
# 1. 修改依赖
vim backend/requirements.txt

# 2. 重建镜像
./start-dev.sh --rebuild

# 3. 测试新依赖
docker compose exec backend python -c "import new_package"
```

### 排查问题工作流

```bash
# 1. 停止服务
docker compose down

# 2. 清理镜像
docker rmi scitool-backend:dev

# 3. 强制重建（清理缓存）
./start-dev.sh --rebuild

# 4. 查看详细日志
docker compose logs backend
```

## 📚 相关命令

### 手动操作

```bash
# 如果不使用启动脚本，手动操作：

# 1. 创建网络
docker network create cpumodel

# 2. 构建镜像（仅首次或修改依赖后）
docker compose build backend

# 3. 启动服务
docker compose up -d

# 4. 查看状态
docker compose ps

# 5. 查看日志
docker compose logs -f backend

# 6. 停止服务
docker compose down
```

### 镜像管理

```bash
# 查看镜像
docker images | grep scitool-backend

# 删除镜像
docker rmi scitool-backend:dev

# 查看镜像详情
docker image inspect scitool-backend:dev

# 清理所有未使用的镜像
docker image prune -a
```

## 🚦 启动脚本返回值

| 返回值 | 含义 | 处理方式 |
|--------|------|----------|
| 0 | 成功启动 | - |
| 1 | Docker 未安装/未运行 | 安装/启动 Docker |
| 1 | Compose 未安装 | 安装 docker-compose |
| 1 | 网络创建失败 | 检查 Docker 网络权限 |

## 📖 参考文档

- [开发环境指南](./DEVELOPMENT.md)
- [快速开始](./QUICKSTART.md)
- [Docker Compose 配置](./docker-compose.yml)

---

**总结**: 使用 `./start-dev.sh --quick` 进行日常开发，享受快速启动体验！🚀
