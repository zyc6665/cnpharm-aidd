# ============================================================================
# SciTool Backend - Python FastAPI + Celery
# ============================================================================
#
# 多阶段构建 Dockerfile
# - development: 开发环境（包含调试工具）
# - production: 生产环境（精简镜像）
#
# 使用方法:
#   开发: docker build --target development -t scitool-backend:dev .
#   生产: docker build --target production -t scitool-backend:prod .
#
# ============================================================================

# ========== 基础镜像 ==========
FROM python:3.11-slim AS base

WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ========== 依赖构建阶段 ==========
FROM base AS builder

# 安装编译依赖（仅用于构建 Python 包）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
# 使用 wheel 加速后续阶段的安装
RUN pip install --upgrade pip && \
    pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ========== 开发阶段 ==========
FROM base AS development

# 安装运行时依赖 + 编译工具（开发需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    vim \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 复制预编译的 wheels
COPY --from=builder /wheels /wheels
COPY requirements.txt .

# 安装所有依赖（使用预编译的 wheels，更快）
RUN pip install --upgrade pip && \
    pip install --no-cache /wheels/* && \
    rm -rf /wheels

# 创建必要的目录
RUN mkdir -p /app/storage/uploads /app/storage/logs

# 暴露端口
EXPOSE 8000

# 健康检查（修正路径）
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/system/health || exit 1

# 开发模式默认命令（支持热重载）
# 注意: 代码通过 volume 挂载，不需要 COPY
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/app"]

# ========== 生产阶段 ==========
FROM python:3.11-slim AS production

WORKDIR /app

# 仅安装运行时依赖（不需要编译工具）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 复制预编译的 wheels
COPY --from=builder /wheels /wheels
COPY requirements.txt .

# 安装依赖（使用预编译的 wheels）
RUN pip install --upgrade pip && \
    pip install --no-cache /wheels/* && \
    rm -rf /wheels

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p storage/uploads storage/logs && \
    chmod 755 /app/storage

# 暴露端口
EXPOSE 8000

# 健康检查（修正路径）
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/system/health || exit 1

# 生产模式默认命令（多进程）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

# ============================================================================
# 构建命令参考
# ============================================================================
#
# 开发环境构建:
#   docker build --target development -t scitool-backend:dev .
#
# 生产环境构建:
#   docker build --target production -t scitool-backend:prod .
#
# 查看镜像大小:
#   docker images | grep scitool-backend
#
# 镜像大小对比:
#   开发镜像: ~650MB (包含编译工具和调试工具)
#   生产镜像: ~450MB (精简，仅运行时依赖)
#
# ============================================================================
