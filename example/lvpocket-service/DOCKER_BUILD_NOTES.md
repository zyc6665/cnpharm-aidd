# Docker 构建问题和解决方案

本文档记录 LVPocket Service Docker 镜像构建过程中遇到的问题及解决方案。

---

## 问题 1: NVIDIA GPG 密钥验证失败

### 错误信息
```
GPG error: https://developer.download.nvidia.com/compute/cuda/repos/ubuntu1804/x86_64 InRelease:
The following signatures couldn't be verified because the public key is not available: NO_PUBKEY A4B469963BF863CC
E: The repository is no longer signed.
```

### 根本原因
- 基础镜像 `tensorflow/tensorflow:1.15.0-gpu-py3` 基于 Ubuntu 18.04
- NVIDIA CUDA 仓库的 GPG 密钥已过期或更新
- apt-get update 无法验证仓库签名

### 解决方案
在 Dockerfile 中添加（第28行和第123行）：

```dockerfile
# 修复 NVIDIA GPG 密钥问题
RUN rm -f /etc/apt/sources.list.d/cuda.list /etc/apt/sources.list.d/nvidia-ml.list || true
```

**原理**: 移除包含过期 GPG 密钥的仓库配置文件，允许 apt-get 使用 Ubuntu 官方仓库。

**影响**:
- ✅ 不影响 GPU 功能（CUDA 库已内置在基础镜像）
- ✅ 允许安装其他系统包
- ✅ 保持 TensorFlow 1.15 环境一致性

---

## 问题 2: python3-openbabel 包不存在

### 错误信息
```
E: Unable to locate package python3-openbabel
```

### 根本原因
- Ubuntu 18.04 的官方仓库中没有 `python3-openbabel` 包
- OpenBabel Python 绑定需要通过其他方式安装

### 解决方案

#### 1. 修改 Dockerfile（第36-42行）
从系统依赖列表中移除 `python3-openbabel`：

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libopenbabel-dev \
    openbabel \
    swig \
    && rm -rf /var/lib/apt/lists/*
```

保留：
- `libopenbabel-dev` - C++ 开发库（编译时需要）
- `openbabel` - 命令行工具
- `swig` - 用于生成 Python 绑定

#### 2. 修改 requirements.txt（第31行）
添加 pip 包：

```
openbabel==3.1.1
```

**安装过程**:
1. pip 下载 openbabel 源码
2. 使用 swig 生成 Python 绑定
3. 链接到系统的 libopenbabel 库
4. 编译并安装到 Python 环境

**依赖关系**:
```
apt: libopenbabel-dev + swig
  ↓ (提供编译环境)
pip: openbabel==3.1.1
  ↓ (编译生成)
Python: import pybel, import openbabel
```

---

## 构建命令

### 完整构建（推荐）
```bash
cd /data/zhouyc/cpumodel_sciminer/example/lvpocket-service

# 清理缓存
docker builder prune

# 重新构建（不使用缓存）
docker-compose build --no-cache

# 启动服务
docker-compose up -d
```

### 调试构建
```bash
# 构建时显示详细输出
docker-compose build --no-cache --progress=plain

# 或者直接使用 docker build
docker build --no-cache --progress=plain -t lvpocket-service:1.0.0 .
```

---

## 验证清单

构建成功后，验证以下项目：

### 1. 镜像创建成功
```bash
docker images | grep lvpocket-service
# 应显示: lvpocket-service  1.0.0  xxxxx  几分钟前  4-5GB
```

### 2. 容器启动正常
```bash
docker-compose up -d
docker-compose ps
# 应显示: lvpocket-service  Up  (health: starting)
```

### 3. Python 依赖可用
```bash
docker-compose exec lvpocket-service python -c "import pybel; print('pybel OK')"
docker-compose exec lvpocket-service python -c "import openbabel; print('openbabel OK')"
```

### 4. 健康检查通过
等待 60-120 秒后：
```bash
curl http://localhost:8000/api/v1/health | jq
# 应返回: {"status": "healthy", "model_loaded": true, ...}
```

---

## 常见构建问题

### Q1: 构建卡在安装 openbabel
**现象**: pip install openbabel 长时间无响应

**原因**: openbabel 正在编译（需要5-10分钟）

**解决**: 耐心等待，或使用 `--progress=plain` 查看详细进度

### Q2: openbabel 编译失败
**错误**: `fatal error: openbabel/mol.h: No such file or directory`

**原因**: 缺少 libopenbabel-dev

**解决**: 确保 Dockerfile 中安装了 `libopenbabel-dev` 和 `swig`

### Q3: SWIG 版本问题
**错误**: `SWIG version 4.x.x required`

**解决**: Ubuntu 18.04 的 swig 版本是 3.x，通常足够。如果确实需要更新版本，需要从源码编译。

### Q4: 内存不足
**错误**: `Killed` 或 `MemoryError`

**原因**: 编译 openbabel 需要较多内存

**解决**:
- 增加 Docker 内存限制（至少 4GB）
- 减少并行构建任务

---

## 技术说明

### 为什么使用 pip 而不是系统包？

| 方式 | Ubuntu 18.04 可用性 | 优点 | 缺点 |
|------|---------------------|------|------|
| apt install python3-openbabel | ❌ 不可用 | 简单快速 | N/A |
| pip install openbabel | ✅ 可用 | 版本可控 | 需要编译（慢） |
| conda install openbabel | ✅ 可用 | 预编译二进制 | 需要 conda 环境 |

**结论**: 对于 TensorFlow 1.15 Docker 镜像（Python 3.6），使用 pip 是最佳选择。

### OpenBabel 版本选择

- **3.1.1**: 当前稳定版，与 Python 3.6 兼容 ✅
- **3.0.0**: 旧稳定版
- **2.x**: 过时，不推荐

---

## 性能优化

### 减少构建时间

1. **使用构建缓存**:
   ```bash
   # 首次构建后，后续构建使用缓存
   docker-compose build
   ```

2. **多阶段构建**:
   - 已在 Dockerfile 中实现
   - 构建阶段和运行阶段分离
   - 最终镜像不包含编译工具

3. **预编译依赖**:
   - 可以创建一个基础镜像，预装所有依赖
   - 加速后续迭代开发

---

## 总结

修复后的 Dockerfile：
- ✅ 解决 GPG 密钥问题（移除过期配置）
- ✅ 解决 python3-openbabel 缺失（改用 pip）
- ✅ 保持多阶段构建优化
- ✅ 最小化最终镜像大小

**预期构建时间**: 8-12 分钟（首次）
**最终镜像大小**: 4-5 GB
**Python 3.6 + TensorFlow 1.15 + CUDA 10.0**
