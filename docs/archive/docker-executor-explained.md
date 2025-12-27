# Docker 执行器工作原理

## 🎯 什么是 Docker 执行器？

Docker 执行器允许后端在 Docker 容器中运行科学计算工具，提供：
- 🔒 **隔离环境** - 每个任务在独立容器中运行
- 📦 **依赖管理** - 工具的依赖打包在镜像中
- 🚀 **可复现性** - 确保环境一致
- 💪 **GPU 支持** - 可以分配 GPU 资源

## 🏗️ 架构设计

### Docker-in-Docker (DinD) 模式

```
┌─────────────────────────────────────────────────────────┐
│                    宿主机 (Host)                          │
│                                                          │
│  ┌────────────────────────────────────────────────┐    │
│  │          Docker 引擎 (Docker Daemon)            │    │
│  │                                                 │    │
│  │  /var/run/docker.sock  ◄───────────┐          │    │
│  └────────────────────────────────────│───────────┘    │
│                                        │                 │
│  ┌─────────────────────────────────┐ │                 │
│  │   后端容器 (Backend Container)    │ │                 │
│  │                                  │ │                 │
│  │  ┌────────────────────────────┐ │ │                 │
│  │  │  Python Docker SDK         │ │ │                 │
│  │  │  ↓                         │ │ │                 │
│  │  │  /var/run/docker.sock ─────┼─┘ │  (挂载)        │
│  │  └────────────────────────────┘   │                 │
│  │                                    │                 │
│  │  DockerExecutor.execute()          │                 │
│  │    ↓                               │                 │
│  │  创建任务容器 ──────────────────────┼─────┐           │
│  └────────────────────────────────────┘     │           │
│                                              │           │
│  ┌──────────────────────────────────────────┼─────┐     │
│  │   任务容器 (Task Container)              │     │     │
│  │                                          ↓     │     │
│  │   运行科学计算工具                             │     │
│  │   (例如: alpine, python, cuda 等)              │     │
│  └────────────────────────────────────────────────┘     │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## 🔧 技术实现

### 1. Docker Socket 挂载

**docker-compose.yml 配置**:
```yaml
services:
  backend:
    volumes:
      # 挂载宿主机的 Docker socket
      - /var/run/docker.sock:/var/run/docker.sock
```

**作用**:
- 后端容器可以通过 socket 与宿主机 Docker 引擎通信
- 创建的任务容器实际运行在**宿主机**上（不是嵌套容器）
- 共享宿主机的 Docker 网络和资源

### 2. Python Docker SDK

**requirements.txt**:
```txt
docker==7.0.0  # Docker SDK for Python
```

**代码示例** (`backend/app/tasks/executor.py`):
```python
import docker

class DockerExecutor(BaseExecutor):
    async def execute(self) -> Dict[str, Any]:
        # 连接到 Docker（通过挂载的 socket）
        client = docker.from_env()

        # 创建并运行容器
        container = client.containers.run(
            image=self.config['docker_image'],
            command=self.config.get('command'),
            environment=self.config.get('environment', {}),
            volumes=self._prepare_volumes(),
            network='cpumodel',  # 使用相同网络
            remove=True,         # 运行后自动删除
            detach=False         # 等待完成
        )

        return {"output": container.decode('utf-8')}
```

### 3. 不需要安装 Docker CLI

**之前的错误做法** ❌:
```dockerfile
# Dockerfile
RUN apt-get install docker.io  # 安装完整 Docker 引擎（100+ MB）
```

**正确做法** ✅:
```dockerfile
# Dockerfile
# 不需要安装 docker.io
# Python Docker SDK 直接通过 socket 通信
```

**原因**:
1. Python Docker SDK 使用 **HTTP over Unix Socket** 协议
2. 直接与 `/var/run/docker.sock` 通信
3. 不需要 Docker CLI 或 Docker 引擎

## 📊 执行流程

### 完整流程示例

```python
# 1. 用户通过 API 创建任务
POST /api/v1/tasks
{
    "tool_id": "xxx",
    "params": {"input": "data.txt"}
}

# 2. API 将任务入队
task = Task(status=PENDING)
TaskQueueManager.enqueue_task(task.id, tool_version.id)

# 3. Celery Worker 接收任务
@shared_task
def execute_tool_task(task_id, tool_version_id):
    # 获取工具配置
    tool_version = get_tool_version(tool_version_id)

    # 创建执行器
    executor = TaskExecutor(
        tool_config=tool_version.config,
        params=params
    )

    # 执行任务
    result = await executor.execute()

# 4. DockerExecutor 执行
class DockerExecutor:
    async def execute(self):
        # 连接 Docker
        client = docker.from_env()

        # 创建容器
        container = client.containers.run(
            image='alpine:latest',
            command=['echo', 'Hello from Docker!'],
            network='cpumodel'
        )

        # 返回结果
        return {"output": container.decode()}

# 5. 宿主机 Docker 创建并运行容器
# 任务容器与后端容器在同一网络中运行

# 6. 结果返回给用户
WebSocket → 实时进度更新
```

## 🔐 安全考虑

### 风险

1. **容器逃逸风险**
   - 挂载 Docker socket 相当于给予容器 root 权限
   - 恶意代码可以创建特权容器

2. **资源耗尽**
   - 任务容器可能消耗大量资源
   - 需要设置资源限制

### 安全措施

```python
# backend/app/tasks/executor.py
class DockerExecutor:
    async def execute(self):
        client = docker.from_env()

        container = client.containers.run(
            image=self.config['docker_image'],

            # ===== 安全配置 =====

            # 资源限制
            mem_limit='2g',           # 内存限制
            cpu_period=100000,        # CPU 周期
            cpu_quota=50000,          # CPU 配额（50%）

            # 网络隔离
            network='cpumodel',       # 使用专用网络

            # 禁止特权模式
            privileged=False,         # 不允许特权容器

            # 只读文件系统（可选）
            read_only=True,           # 根文件系统只读

            # 运行后自动删除
            remove=True,              # 防止容器堆积

            # 超时控制
            timeout=3600,             # 1小时超时
        )
```

## 🎓 工具配置示例

### 示例1: Alpine Echo 工具

```json
{
    "executor_type": "docker",
    "docker_image": "alpine:latest",
    "command": ["echo", "Hello, World!"],
    "environment": {
        "TZ": "Asia/Shanghai"
    }
}
```

### 示例2: Python 脚本工具

```json
{
    "executor_type": "docker",
    "docker_image": "python:3.11-slim",
    "command": ["python", "-c", "print('Hello from Python')"],
    "volumes": {
        "/app/data": "/data"  # 挂载数据目录
    }
}
```

### 示例3: GPU 加速工具

```json
{
    "executor_type": "docker",
    "docker_image": "nvidia/cuda:11.8-runtime",
    "command": ["nvidia-smi"],
    "device_requests": [
        {
            "driver": "nvidia",
            "count": 1,
            "capabilities": [["gpu"]]
        }
    ]
}
```

## 📝 测试 Docker 执行器

### 手动测试

```bash
# 1. 确保后端容器运行中
docker compose ps backend

# 2. 进入后端容器
docker compose exec backend bash

# 3. 测试 Docker SDK
python
>>> import docker
>>> client = docker.from_env()
>>> client.version()  # 应该返回宿主机 Docker 版本
>>>
>>> # 测试创建容器
>>> container = client.containers.run(
...     'alpine:latest',
...     'echo "Hello from container"',
...     remove=True
... )
>>> print(container)  # 应该输出: b'Hello from container\n'
```

### API 测试

```bash
# 创建一个测试任务（需要先创建对应的工具）
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "tool_id": "docker-echo-tool",
    "params": {
      "message": "Hello from API"
    }
  }'

# 查看任务执行日志
docker compose logs -f celery-worker
```

## 🐛 故障排查

### 问题1: 无法连接 Docker

**错误信息**:
```
docker.errors.DockerException: Error while fetching server API version
```

**解决方案**:
```bash
# 检查 socket 挂载
docker compose exec backend ls -la /var/run/docker.sock

# 检查权限
docker compose exec backend stat /var/run/docker.sock

# 重新启动容器
docker compose restart backend
```

### 问题2: 容器创建失败

**错误信息**:
```
docker.errors.ImageNotFound: 404 Client Error: Not Found
```

**解决方案**:
```bash
# 在宿主机上拉取镜像
docker pull alpine:latest

# 或在工具配置中使用已存在的镜像
```

### 问题3: 网络连接问题

**错误信息**:
```
network cpumodel not found
```

**解决方案**:
```bash
# 创建网络
docker network create cpumodel

# 确认任务容器使用相同网络
```

## 📚 相关文档

- [Docker SDK for Python 文档](https://docker-py.readthedocs.io/)
- [Docker API 参考](https://docs.docker.com/engine/api/)
- [任务执行器实现](../backend/app/tasks/executor.py)
- [Docker 安全最佳实践](https://docs.docker.com/engine/security/)

## 💡 总结

Docker 执行器的关键点：

1. ✅ **不需要在容器内安装 Docker CLI**
   - Python Docker SDK 直接通过 socket 通信

2. ✅ **挂载 Docker socket 是必需的**
   - `/var/run/docker.sock:/var/run/docker.sock`

3. ✅ **任务容器运行在宿主机上**
   - 不是嵌套容器
   - 共享宿主机资源和网络

4. ⚠️ **注意安全风险**
   - 设置资源限制
   - 禁用特权模式
   - 使用隔离网络

5. 🎯 **适用场景**
   - 需要隔离环境的计算任务
   - 有复杂依赖的科学计算工具
   - GPU 加速任务
