# ============================================================================
# LVPocket Service Dockerfile
# ============================================================================
#
# 构建命令:
#   docker build -t lvpocket-service:1.0.0 .
#
# 运行命令 (GPU):
#   docker run --gpus all -p 8000:8000 lvpocket-service:1.0.0
#
# 运行命令 (CPU):
#   docker run -p 8000:8000 lvpocket-service:1.0.0
#
# ============================================================================

# ============================================
# 阶段1: 构建阶段 - 安装依赖
# ============================================
FROM tensorflow/tensorflow:1.15.0-gpu-py3 AS builder

# 设置环境变量，避免交互式安装
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# 安装系统依赖
# - build-essential: 编译工具
# - cmake: 构建系统
# - libopenbabel-dev/openbabel: 分子处理库
# - swig: 接口生成器
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libopenbabel-dev \
    openbabel \
    python3-openbabel \
    swig \
    && rm -rf /var/lib/apt/lists/*

# 升级 pip
RUN python -m pip install --upgrade pip setuptools wheel

# 复制依赖文件
COPY requirements.txt /tmp/requirements.txt

# 安装 Python 依赖
RUN pip install --no-cache-dir -r /tmp/requirements.txt


# ============================================
# 阶段2: 运行阶段
# ============================================
FROM tensorflow/tensorflow:1.15.0-gpu-py3

# ---------- 基础环境变量 ----------
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
# 禁用 Python 输出缓冲
ENV PYTHONUNBUFFERED=1
# 禁止生成 .pyc 文件
ENV PYTHONDONTWRITEBYTECODE=1

# ---------- TensorFlow 配置 ----------
# 日志级别: 0=全部, 1=过滤INFO, 2=过滤WARNING, 3=过滤ERROR
ENV TF_CPP_MIN_LOG_LEVEL=2
# 允许 GPU 内存动态增长（推荐）
ENV TF_FORCE_GPU_ALLOW_GROWTH=true

# ---------- 应用配置 ----------
ENV APP_NAME="LVPocket Service"
ENV APP_VERSION="1.0.0"
# 监听地址，0.0.0.0 表示所有网卡
ENV HOST=0.0.0.0
# 监听端口
ENV PORT=8000
# Uvicorn worker 数量
ENV WORKERS=1
# 日志级别: DEBUG | INFO | WARNING | ERROR
ENV LOG_LEVEL=INFO

# ---------- LVpocket 配置 ----------
# LVpocket 源代码路径（用于导入 model.LV_former 和 tfbio.data）
# 目录结构: /app/model/LVpocket/
ENV LVPOCKET_SOURCE_PATH=/app/model/LVpocket

# ---------- 模型配置 ----------
# 模型目录（包含所有 SCOP 分类模型）
ENV MODEL_DIR=/app/model/LVpocket/trained_model
# 模型文件路径（参考 predict.py）- 保持兼容
ENV MODEL_PATH=/app/model/LVpocket/trained_model/scale_0.5_1.h5
ENV MODEL_VERSION=1.0.0
# 体素分辨率 (Å)，参考 predict.py --scale 默认值
ENV SCALE=0.5
# 最大距离阈值，参考 predict.py --max_dist 默认值
ENV MAX_DIST=35.0

# ---------- 多模型配置（SCOP 结构分类）----------
# 默认使用的结构分类模型
# 可选值: baseline | alpha | beta | alpha_beta | alpha_plus_beta
ENV DEFAULT_STRUCTURE_CLASS=baseline

# ---------- 预测参数 ----------
# 默认口袋预测阈值 (0-1)
ENV DEFAULT_THRESHOLD=0.5
# 默认最小口袋体素数
ENV DEFAULT_MIN_SIZE=50

# ---------- 文件配置 ----------
# 临时文件目录
ENV TEMP_DIR=/tmp/lvpocket
# 输出文件目录
ENV OUTPUT_DIR=/app/data/output
# 最大上传文件大小 (bytes)，默认 50MB
ENV MAX_FILE_SIZE=52428800

# 安装运行时依赖
# - libopenbabel6: OpenBabel 运行时库
# - curl: 健康检查
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenbabel6 \
    openbabel \
    python3-openbabel \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段复制 Python 包
COPY --from=builder /usr/local/lib/python3.6/dist-packages /usr/local/lib/python3.6/dist-packages

# 设置工作目录
WORKDIR /app

# 创建必要目录
RUN mkdir -p /app/model /app/data/input /app/data/output /tmp/lvpocket

# 复制 model 目录（包含 LVpocket 源码和模型文件）
# 目录结构:
#   model/
#   └── LVpocket/
#       ├── model/           # LV_former.py
#       ├── tfbio/           # data.py
#       ├── scripts/
#       └── trained_model/   # scale_0.5_1.h5
COPY model/ /app/model/

# 复制应用代码
COPY app/ /app/app/

# 创建非 root 用户（安全最佳实践）
RUN groupadd -r lvpocket && useradd -r -g lvpocket lvpocket \
    && chown -R lvpocket:lvpocket /app /tmp/lvpocket

# 切换到非 root 用户
USER lvpocket

# 健康检查
# - interval: 检查间隔
# - timeout: 超时时间
# - start_period: 启动等待时间（模型加载需要时间）
# - retries: 失败重试次数
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/v1/health || exit 1

# 暴露端口
EXPOSE ${PORT}

# 启动命令
# 使用 uvicorn 运行 FastAPI 应用
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ============================================================================
# 构建说明
# ============================================================================
#
# 1. 目录结构要求:
#    lvpocket-service/
#    ├── Dockerfile
#    ├── requirements.txt
#    ├── app/                    # API 服务代码
#    │   ├── main.py
#    │   ├── config.py
#    │   ├── api/
#    │   └── core/
#    └── model/
#        └── LVpocket/           # LVpocket 源码
#            ├── model/
#            │   └── LV_former.py
#            ├── tfbio/
#            │   └── data.py
#            └── trained_model/
#                ├── scale_0.5_1.h5      # baseline 模型（必需）
#                ├── alpha_model.h5       # α 类模型（可选）
#                ├── beta_model.h5        # β 类模型（可选）
#                ├── alpha_beta_model.h5  # α/β 类模型（可选）
#                └── alpha_plus_beta_model.h5  # α+β 类模型（可选）
#
# 2. 模型文件下载:
#    从 Zenodo 下载: https://doi.org/10.5281/zenodo.10633690
#
# 3. SCOP 结构分类模型说明:
#    - baseline: 基线模型，适用于所有蛋白质（默认）
#    - alpha: α 类蛋白质，主要由 α 螺旋组成
#    - beta: β 类蛋白质，主要由 β 折叠组成
#    - alpha_beta: α/β 类蛋白质，α 螺旋和 β 折叠交替排列
#    - alpha_plus_beta: α+β 类蛋白质，α 螺旋和 β 折叠分离排列
#
# 4. 多阶段构建优势:
#    - 减小最终镜像大小
#    - 不包含构建工具
#    - 更安全
#
# ============================================================================
