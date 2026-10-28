# LVpocket-2 模型镜像（TensorFlow 2.15 / CUDA 12.2 运行时随 pip 包自带）
#
# 构建上下文：本目录 = Dockerfile + model/ + platform_adaptor/
#   model/              模型代码（含 6 处 TF2 兼容修复）、platform_run.sh、requirements.txt
#   platform_adaptor/   平台适配层（entrypoint.sh -> platform_run_v2.sh -> object_storage.py）
# 两者由 `./build.sh prepare` 从源目录准备，不入库。
#
# 权重不打包：19 GB 的 new_best/ 由 runtime.weights 只读挂到 /opt/sciminer/model/new_best。
# 容器启动时若该目录为空，platform_run.sh 找不到 .hdf 会立即失败（fail fast，不会静默跑错结果）。
#
# 为什么不用 nvidia/cuda 基础镜像：
#   tensorflow[and-cuda] 的 wheel 自带 CUDA 12.2 / cuDNN 运行时，不依赖宿主 CUDA 库，
#   因此 python:*-slim 足够，镜像更小；迁移到 DCU 时也只需替换 tensorflow 包所在的那一层。
ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNOUSERSITE=1 \
    MODEL_PACKAGE_ROOT=/opt/sciminer/model \
    PLATFORM_ADAPTOR_ROOT=/opt/sciminer/platform_adaptor \
    MODEL_PYTHON=/usr/local/bin/python \
    PYTHONPATH=/opt/sciminer/model \
    TF_CPP_MIN_LOG_LEVEL=2

WORKDIR /opt/sciminer

# tcsh + ncbi-blast+ 是 PSIPRED 分类链路的依赖（与原环境一致）；
# libxrender1 / libxext6 是 OpenBabel 的 dmolformat 插件所需的 X 库（缺失只告警，但会刷屏）。
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
         ca-certificates tini tcsh ncbi-blast+ libgomp1 libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

COPY model/requirements.txt /opt/sciminer/model/requirements.txt
RUN python -m pip install --no-cache-dir \
        -i https://pypi.tuna.tsinghua.edu.cn/simple --upgrade pip \
    && python -m pip install --no-cache-dir \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        -r /opt/sciminer/model/requirements.txt

COPY platform_adaptor /opt/sciminer/platform_adaptor
# openbabel-wheel 3.1.1.23 的 pybel 模块在 import 时就崩，必须在镜像里修库（见 shared/patch_openbabel.py）
RUN python /opt/sciminer/platform_adaptor/patch_openbabel.py
COPY model /opt/sciminer/model

# 权重挂载点（空目录，运行时由 runtime.weights 覆盖）
# env/bin/python 软链：模型入口脚本里硬编码了 model_root/env/bin/python，而镜像里解释器在 /usr/local/bin
RUN mkdir -p /opt/sciminer/model/new_best /opt/sciminer/model/env/bin \
    && ln -sfn /usr/local/bin/python /opt/sciminer/model/env/bin/python \
    && ln -sfn /usr/local/lib /opt/sciminer/model/env/lib \
    && chmod +x /opt/sciminer/model/platform_run.sh \
    && chmod +x /opt/sciminer/platform_adaptor/*.sh \
    && python -c "import tensorflow as tf; print('tf', tf.__version__, 'py', __import__('sys').version.split()[0])"

ENTRYPOINT ["/usr/bin/tini", "--", "/opt/sciminer/platform_adaptor/entrypoint.sh"]
