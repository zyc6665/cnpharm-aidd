# ============================================================================
# LVPocket Service Dockerfile - Python 3.8 现代化方案
# ============================================================================
#
# 基于 NVIDIA NGC TensorFlow 1.15 镜像 (Python 3.8)，使用转换后的兼容模型
#
# 构建命令:
#   docker build -t lvpocket-service:1.0.0 .
#
# 运行命令 (GPU):
#   docker run --gpus all -p 9502:9502 lvpocket-service:1.0.0
#
# 运行命令 (CPU):
#   docker run -p 9502:9502 -e CUDA_VISIBLE_DEVICES="" lvpocket-service:1.0.0
#
# ============================================================================

# ============================================
# 阶段1: 构建阶段 - 编译依赖
# ============================================
# 使用 NVIDIA NGC TensorFlow 1.15 镜像 (Python 3.8, CUDA 11.0)
FROM nvcr.io/nvidia/tensorflow:20.12-tf1-py3 AS builder

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# -------- 安装系统依赖 --------
# build-essential: 编译工具链
# cmake: 构建系统
# swig: Python 绑定生成器
# libeigen3-dev: 线性代数库 (OpenBabel 依赖)
# libboost-all-dev: Boost 库 (OpenBabel 依赖)
# libcairo2-dev: 2D 图形库 (OpenBabel 可选)
# rapidjson-dev: JSON 解析 (OpenBabel 3.x 依赖)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    swig \
    python3-dev \
    libeigen3-dev \
    libboost-all-dev \
    libcairo2-dev \
    rapidjson-dev \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# -------- 编译安装 OpenBabel 3.1.1 --------
# OpenBabel 3.x 优势:
# - 更好的 Python 3 支持
# - 更稳定的 SWIG 绑定
# - 持续维护
ARG OPENBABEL_VERSION=3.1.1
RUN cd /tmp && \
    wget -q https://github.com/openbabel/openbabel/archive/refs/tags/openbabel-3-1-1.tar.gz && \
    tar xzf openbabel-3-1-1.tar.gz && \
    cd openbabel-openbabel-3-1-1 && \
    mkdir build && cd build && \
    cmake .. \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DPYTHON_EXECUTABLE=/usr/bin/python3 \
        -DPYTHON_BINDINGS=ON \
        -DRUN_SWIG=ON \
        -DWITH_COORDGEN=OFF \
        -DWITH_MAEPARSER=OFF \
        -DBUILD_GUI=OFF && \
    make -j$(nproc) && \
    make install && \
    ldconfig && \
    cd /tmp && rm -rf openbabel-*

# 验证 OpenBabel 安装
RUN python3 -c "from openbabel import pybel; print(f'OpenBabel {pybel.ob.OBReleaseVersion()} OK')"

# -------- 创建 pybel 兼容层 --------
# OpenBabel 3.x 使用 `from openbabel import pybel`
# 但 tfbio 和 LVPocket 使用旧式 `import pybel`
# 创建兼容层使两种导入方式都能工作
RUN echo 'from openbabel.pybel import *' > /usr/local/lib/python3.8/dist-packages/pybel.py && \
    echo 'from openbabel import openbabel' > /usr/local/lib/python3.8/dist-packages/openbabel_compat.py

# 验证兼容层
RUN python3 -c "import pybel; print('pybel compat OK')"

# -------- 安装 tfbio --------
# tfbio 仅在 conda cheminfIBB 频道提供，从本地复制安装
# 这是 LVPocket 的核心依赖，提供分子特征化和网格生成功能
COPY tfbio /opt/tfbio
RUN cd /opt/tfbio && pip install --no-cache-dir -e .

# 验证 tfbio 安装
RUN python3 -c "import tfbio.data; print('tfbio OK')"

# -------- 升级 pip 并安装 Python 依赖 --------
RUN pip install --upgrade pip setuptools wheel -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    --timeout 120

# 验证关键依赖
RUN python3 -c "import tensorflow as tf; print(f'TensorFlow {tf.__version__} OK')" && \
    python3 -c "import keras; print(f'Keras {keras.__version__} OK')" && \
    python3 -c "import numpy; print(f'NumPy {numpy.__version__} OK')" && \
    python3 -c "import scipy; print(f'SciPy {scipy.__version__} OK')" && \
    python3 -c "import skimage; print(f'scikit-image {skimage.__version__} OK')"


# ============================================
# 阶段2: 运行阶段
# ============================================
FROM nvcr.io/nvidia/tensorflow:20.12-tf1-py3

# ---------- 基础环境变量 ----------
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# ---------- TensorFlow 配置 ----------
ENV TF_CPP_MIN_LOG_LEVEL=2
ENV TF_FORCE_GPU_ALLOW_GROWTH=true
# 禁用 TF 自动混合精度（保持与原始模型兼容）
ENV TF_ENABLE_AUTO_MIXED_PRECISION=0

# ---------- 应用配置 ----------
ENV APP_NAME="LVPocket Service"
ENV APP_VERSION="1.0.0"
ENV HOST=0.0.0.0
ENV PORT=9502
ENV WORKERS=1
ENV LOG_LEVEL=INFO

# ---------- LVpocket 配置 ----------
ENV LVPOCKET_SOURCE_PATH=/app/model/LVpocket
ENV MODEL_DIR=/app/model/LVpocket/trained_model
ENV MODEL_PATH=/app/model/LVpocket/trained_model/newbest/new_best/baseline_model.hdf
ENV MODEL_VERSION=1.0.0
ENV SCALE=0.5
ENV MAX_DIST=35.0
ENV DEFAULT_STRUCTURE_CLASS=baseline

# ---------- 预测参数 ----------
ENV DEFAULT_THRESHOLD=0.5
ENV DEFAULT_MIN_SIZE=50

# ---------- 文件配置 ----------
ENV TEMP_DIR=/tmp/lvpocket
ENV OUTPUT_DIR=/app/data/output
ENV MAX_FILE_SIZE=52428800

# -------- 安装运行时依赖 --------
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libboost-all-dev \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# -------- 从构建阶段复制 OpenBabel --------
# 复制库文件
COPY --from=builder /usr/local/lib/libopenbabel* /usr/local/lib/
COPY --from=builder /usr/local/lib/libinchi* /usr/local/lib/
COPY --from=builder /usr/local/lib/openbabel /usr/local/lib/openbabel

# 复制 OpenBabel Python 绑定 (Python 3.8)
COPY --from=builder /usr/local/lib/python3.8/dist-packages/openbabel /usr/local/lib/python3.8/dist-packages/openbabel
COPY --from=builder /usr/local/lib/python3.8/dist-packages/pybel.py /usr/local/lib/python3.8/dist-packages/pybel.py

# -------- 从构建阶段复制 tfbio --------
COPY --from=builder /opt/tfbio /opt/tfbio
ENV PYTHONPATH=/opt/tfbio:$PYTHONPATH

# -------- 从构建阶段复制 Python 包 --------
COPY --from=builder /usr/local/lib/python3.8/dist-packages /usr/local/lib/python3.8/dist-packages

# 更新动态链接库缓存
RUN ldconfig

# 验证运行时依赖
RUN python3 -c "from openbabel import pybel; print('openbabel.pybel OK')" && \
    python3 -c "import pybel; print('pybel compat OK')" && \
    python3 -c "import tfbio.data; print('tfbio OK')" && \
    python3 -c "import keras; print('keras OK')"

# -------- 设置工作目录 --------
WORKDIR /app

# 创建必要目录
RUN mkdir -p /app/model /app/data/input /app/data/output /tmp/lvpocket

# -------- 复制应用文件 --------
# 复制 model 目录（包含 LVpocket 源码和转换后的模型文件）
COPY model/ /app/model/

# 复制应用代码
COPY app/ /app/app/

# -------- 安全配置 --------
# 创建非 root 用户
RUN groupadd -r lvpocket && useradd -r -g lvpocket lvpocket \
    && chown -R lvpocket:lvpocket /app /tmp/lvpocket

USER lvpocket

# -------- 健康检查 --------
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/v1/health || exit 1

# 暴露端口
EXPOSE ${PORT}

# -------- 启动命令 --------
# 生产环境不启用 --reload
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9502"]

# ============================================================================
# 构建说明
# ============================================================================
#
# 1. 基础镜像说明:
#    - 使用 NVIDIA NGC TensorFlow 1.15 镜像 (nvcr.io/nvidia/tensorflow:20.12-tf1-py3)
#    - Python 3.8, CUDA 11.0, cuDNN 8.x
#    - 使用转换后的 Python 3.8 兼容模型（已移除优化器权重）
#
# 2. 目录结构要求:
#    lvpocket-service/
#    ├── Dockerfile
#    ├── requirements.txt
#    ├── app/                    # API 服务代码
#    │   ├── main.py
#    │   ├── config.py
#    │   ├── api/
#    │   └── core/
#    ├── tfbio/                  # tfbio 源码（已修复 heavydegree）
#    └── model/
#        └── LVpocket/           # LVpocket 源码
#            ├── model/          # LV_former.py
#            ├── scripts/
#            └── trained_model/  # 转换后的模型文件（Python 3.8 兼容）
#
# 3. 模型文件说明:
#    - 使用 convert_models.py 转换后的模型
#    - 已移除优化器权重，体积减小 69%
#    - 兼容 Python 3.8 + TensorFlow 1.15
#
# 4. SCOP 结构分类模型:
#    - baseline: 基线模型（默认）
#    - alpha: α 类蛋白质
#    - beta: β 类蛋白质
#    - alpha_beta: α/β 类蛋白质
#    - alpha_plus_beta: α+β 类蛋白质
#
# 5. 依赖版本:
#    - TensorFlow: 1.15.5
#    - Keras: 2.3.1 (独立版本，兼容 Python 3.8)
#    - OpenBabel: 3.1.1
#    - tfbio: 0.3 (from source, 已修复 heavydegree)
#    - Python: 3.8
#    - FastAPI: 0.95.0
#    - uvicorn: 0.21.0
#    - NumPy: 1.19.5
#    - SciPy: 1.7.3
#
# 6. 关键修复:
#    - tfbio/tfbio/data.py: heavyvalence → heavydegree (OpenBabel 3.x API)
#    - app/api/routes.py: 移除 prefix，在 main.py 中统一配置
#    - app/main.py: include_router 添加 prefix="/api/v1"
#    - app/core/model_loader_patch.py: 强制 compile=False 加载模型
#
# ============================================================================
